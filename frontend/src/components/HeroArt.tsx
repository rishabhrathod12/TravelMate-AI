/** Decorative landscape drawn inline: no image files and no external requests. */
export function HeroArt() {
  return (
    <svg
      className="hero-art"
      viewBox="0 0 400 200"
      aria-hidden="true"
      focusable="false"
      preserveAspectRatio="xMidYMax slice"
    >
      <circle cx="300" cy="62" r="30" fill="#ffd27a" />
      <path d="M0 150 L70 90 L130 140 L200 70 L280 150 L340 110 L400 150 V200 H0Z" fill="#0a4a5f" opacity="0.55" />
      <path d="M0 175 Q60 150 120 172 T240 170 T400 168 V200 H0Z" fill="#12868f" opacity="0.8" />
      <path d="M0 190 Q80 172 160 188 T320 186 T400 184 V200 H0Z" fill="#0b5f7a" />
    </svg>
  );
}
