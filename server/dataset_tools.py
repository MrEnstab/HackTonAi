"""Dataset helpers. Class IDs match the pinned RF100 source exactly."""
import math

NAMES = ['excavator', 'dump_truck', 'wheel_loader']


def normalise_names(names):
    """Return a contiguous, nonempty, unique class-name list."""
    if isinstance(names, dict):
        if set(names) != set(range(len(names))):
            raise ValueError('Class-name dictionary keys must be contiguous from zero')
        names = [names[index] for index in range(len(names))]
    if not isinstance(names, list) or not names:
        raise ValueError('Class names must be a nonempty list or contiguous dictionary')
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError('Every class name must be a nonempty string')
    if len(set(names)) != len(names):
        raise ValueError('Class names must be unique')
    return names


def parse_labels(text, names=NAMES):
    """Validate YOLO detection labels; reject silent class/coordinate corruption."""
    names = normalise_names(names)
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f'Line {number}: expected class x y width height')
        cls = int(fields[0])
        box = list(map(float, fields[1:]))
        if not 0 <= cls < len(names):
            raise ValueError(f'Line {number}: unsupported class {cls}')
        if not all(math.isfinite(x) and 0 <= x <= 1 for x in box):
            raise ValueError(f'Line {number}: invalid normalized coordinates')
        if box[2] <= 0 or box[3] <= 0:
            raise ValueError(f'Line {number}: empty bounding box')
        rows.append((cls, *box))
    return rows


def select_files(files, limits=(0, 0, 0), seed=42):
    """Pick complete image/annotation pairs; zero limit means the whole split."""
    import random
    from pathlib import PurePosixPath
    available = set(files)
    if len(limits) != 3 or any(n < 0 for n in limits):
        raise ValueError('Specify three nonnegative train/valid/test limits')
    selected = [f for f in ['README.md', 'README.dataset.txt', 'README.roboflow.txt', 'data.yaml'] if f in available]
    rng = random.Random(seed)
    for split, limit in zip(['train', 'valid', 'test'], limits):
        images = sorted(f for f in available if f.startswith(f'{split}/images/') and PurePosixPath(f).suffix.lower() in {'.jpg', '.jpeg', '.png'})
        if not images:
            raise ValueError(f'No images found for {split}')
        rng.shuffle(images)
        for image in images[:limit or None]:
            label = f'{split}/labels/{PurePosixPath(image).stem}.txt'
            if label not in available:
                raise ValueError(f'Missing annotation: {label}')
            selected.extend([image, label])
    return selected


def prepare_dataset(source, destination):
    """Keep official splits, deduplicate decoded pixels, validate every label/image.

    The source files are unchanged. Test wins over valid, valid over train.
    Does not prove independence of similar video frames: camera IDs are unavailable.
    """
    import hashlib
    import json
    import shutil
    from pathlib import Path
    from PIL import Image
    import yaml

    source, destination = Path(source), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite {destination}; choose a new --output')
    temporary = destination.with_name(destination.name + '.preparing')
    if temporary.exists():
        raise FileExistsError(f'Interrupted preparation exists: {temporary}; inspect/remove it first')
    temporary.mkdir(parents=True)
    report = {'names': NAMES, 'splits': {}, 'excluded_duplicates': [],
              'limitation': 'Official split preserved. Exact pixel duplicates removed; near-duplicate/camera leakage still needs human review.'}
    seen = {}
    try:
        for split in ['test', 'valid', 'train']:
            images = sorted((source / split / 'images').glob('*'))
            images = [p for p in images if p.suffix.lower() in {'.jpg', '.jpeg', '.png'}]
            if not images:
                raise ValueError(f'Empty source split: {split}')
            image_dir = temporary / split / 'images'
            label_dir = temporary / split / 'labels'
            image_dir.mkdir(parents=True)
            label_dir.mkdir()
            counts = [0] * len(NAMES)
            saved = 0
            stems = set()
            for image_path in images:
                label_path = source / split / 'labels' / (image_path.stem + '.txt')
                # Missing annotation is an error, NOT a background-only image.
                text = label_path.read_text(encoding='utf-8')
                rows = parse_labels(text)
                with Image.open(image_path) as image:
                    image = image.convert('RGB')
                    image.load()
                    digest = hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()
                if digest in seen:
                    report['excluded_duplicates'].append({'removed': f'{split}/{image_path.name}', 'kept': seen[digest]})
                    continue
                if image_path.stem in stems:
                    raise ValueError(f'Image stem collision: {image_path}')
                stems.add(image_path.stem)
                seen[digest] = f'{split}/{image_path.name}'
                shutil.copy2(image_path, image_dir / image_path.name)
                (label_dir / label_path.name).write_text(text, encoding='utf-8')
                for row in rows:
                    counts[row[0]] += 1
                saved += 1
            if not saved:
                raise ValueError(f'All images removed as duplicates in {split}')
            report['splits'][split] = {'images': saved, 'objects_by_class': dict(zip(NAMES, counts))}
        config = {'path': destination.as_posix(), 'train': 'train/images',
                  'val': 'valid/images', 'test': 'test/images', 'names': NAMES, 'nc': len(NAMES)}
        (temporary / 'data.yaml').write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
        (temporary / 'audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.rename(destination)
    except Exception:
        # Only the staging directory created by this call is removed.
        shutil.rmtree(temporary)
        raise
    return report
