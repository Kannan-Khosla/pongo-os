export default function SectionHeading({ eyebrow, title, body, align = 'left' }) {
  return (
    <header className={`section-heading section-heading--${align}`}>
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {body && <p>{body}</p>}
    </header>
  );
}
