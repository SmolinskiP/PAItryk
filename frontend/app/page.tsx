import { ArrowRight, ChevronDown } from "lucide-react";
import Link from "next/link";

import styles from "./page.module.css";

const features = [
  {
    num: "01",
    title: "Co to jest",
    body: "Klon językowy Patryka — zbudowany z jego notatek, rozmów, maili i wspomnień. Mówi jego stylem, w pierwszej osobie. Nie zmyśla — jeśli czegoś nie wie, powie wprost."
  },
  {
    num: "02",
    title: "Po co to powstało",
    body: "Nie po to, żeby cię do czegokolwiek namówić. Po to, żebyś mogła zobaczyć, kim Patryk jest dziś — sama, w spokoju, bez patrzenia mu w oczy. To informacja dla ciebie, nie prośba do ciebie."
  },
  {
    num: "03",
    title: "Na twoich warunkach",
    body: "Możesz przeczytać i wyjść. Możesz nic nie klikać. A jeśli rozmowa z botem to za wiele — są zagadki, ułożone tylko dla ciebie. Potraktuj to jak grę. Bez ciężaru, w swoim tempie, dla samej przyjemności."
  },
  {
    num: "04",
    title: "Twoje ślady",
    body: "Jest guzik «usuń». Kasuje rozmowę naprawdę — całą, z bazy, bez kopii w tle. Nic nie zostaje, jeśli ty tego nie chcesz."
  }
];

export default function LandingPage() {
  return (
    <div className={styles.landing}>
      <div className={styles.background} aria-hidden>
        <span />
      </div>
      <div className={styles.grain} aria-hidden />

      <section className={styles.hero}>
        <span className={styles.eyebrow}>to jest twoja decyzja.</span>

        <h1 className={styles.headline}>
          <span className={styles.headlineAccent}>pAItryk</span>
        </h1>

        <p className={styles.subtitle}>
          Cyfrowy klon Patryka — zbudowany jego materiałami. <strong>Możesz zostać. Możesz wyjść po sekundzie.</strong>{" "}
          Każdy wybór tutaj jest okej. A jeśli rozmowa z botem to za dużo — są zagadki w stylu Dracula riddle czy ze?t riddle. Wiem, że kiedyś je lubiłaś.
        </p>

        <div className={styles.ctaRow}>
          <Link href="/app" className={styles.cta}>
            <span>Możemy zacząć</span>
            <ArrowRight size={20} strokeWidth={2.4} />
          </Link>
          <Link href="/riddle" className={`${styles.cta} ${styles.ctaRiddle}`}>
            <span>Zagadki &gt; rozmowa</span>
            <ArrowRight size={20} strokeWidth={2.4} />
          </Link>
        </div>

        <div className={styles.scrollHint} aria-hidden>
          <ChevronDown size={16} />
          <span>poczytaj zanim zaczniemy</span>
        </div>
      </section>

      <section className={styles.features}>
        {features.map((feature) => (
          <article key={feature.num} className={styles.featureCard}>
            <span className={styles.featureNum}>{feature.num}</span>
            <h3 className={styles.featureTitle}>{feature.title}</h3>
            <p className={styles.featureBody}>{feature.body}</p>
          </article>
        ))}
      </section>

    </div>
  );
}
