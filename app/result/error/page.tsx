import Image from "next/image";
import Link from "next/link";

export default function ResultErrorPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4 py-10">
      <div className="w-full max-w-xl">
        <h1 className="text-3xl font-bold text-main">Результат проверки</h1>
        <p className="mt-2 text-base text-muted">
          Сравниваем данные по плану и результат анализа снимка. Ниже - сводная
          таблица по технике.
        </p>
        <div className="mt-8 flex flex-col items-center rounded-2xl bg-danger-bg px-6 py-14 text-center">
          <Image src="/main/warning.svg" alt="" width={28} height={28} />
          <p className="mt-4 font-semibold text-main">
            Не удалось обработать снимок
          </p>
          <p className="mt-2 max-w-sm text-sm text-muted">
            Возможно, файл повреждён или недостаточно данных для анализа.
            Попробуйте другой снимок.
          </p>
        </div>
        <Link
          href="/"
          className="mt-6 flex w-full items-center justify-center rounded-xl bg-button py-3.5 text-base font-medium text-button-text"
        >
          Загрузить другой снимок
        </Link>
      </div>
    </div>
  );
}
