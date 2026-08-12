"use client";

/**
 * TRACER — Shared Footer
 * File: components/Footer.jsx
 *
 * Drop-in replacement for the closing color-stripe block used at the
 * bottom of Dashboard.jsx, SeasonPage.jsx, AllTimeRankings.jsx, and
 * TeamPage.jsx. Keeps the stripe, adds a thin social-link row above it.
 */

const mono = "'IBM Plex Mono', monospace";
const C = {
  border: '#EDE8DD', border2: '#E0D9CE',
  text3: '#9A9490',
  acc: '#663399', ut: '#BF5700', uo: '#154733',
};

const SOCIALS = [
  { label: 'X / Twitter', href: 'https://twitter.com/TRACERsports', handle: '@TRACERsports' },
  { label: 'Instagram',   href: 'https://instagram.com/tracersports', handle: '@tracersports' },
];

function XIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.9 2H22l-7.6 8.7L23 22h-6.9l-5.4-7-6.2 7H1.3l8.1-9.3L1 2h7l4.9 6.5L18.9 2Zm-2.4 18h1.9L7.6 4H5.6l10.9 16Z"/>
    </svg>
  );
}

function InstagramIcon({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="18" height="18" rx="5"/>
      <circle cx="12" cy="12" r="4"/>
      <circle cx="17.2" cy="6.8" r="0.6" fill="currentColor" stroke="none"/>
    </svg>
  );
}

const ICONS = { 'X / Twitter': XIcon, 'Instagram': InstagramIcon };

export default function Footer() {
  return (
    <>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 20, padding: '1.25rem 2rem 0.5rem',
      }}>
        <span style={{
          fontFamily: mono, fontSize: 10, color: C.text3,
          textTransform: 'uppercase', letterSpacing: 1.5,
        }}>
          Follow TRACER
        </span>
        <div style={{ display: 'flex', gap: 14 }}>
          {SOCIALS.map(({ label, href, handle }) => {
            const Icon = ICONS[label];
            return (
              <a
                key={label}
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                title={label}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontFamily: mono, fontSize: 11, color: C.text3,
                  textDecoration: 'none', transition: 'color 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.color = C.acc}
                onMouseLeave={e => e.currentTarget.style.color = C.text3}
              >
                <Icon />
                <span>{handle}</span>
              </a>
            );
          })}
        </div>
      </div>

      <div className="color-stripe" style={{ marginTop: '0.75rem' }}>
        <div className="stripe-acc"/><div className="stripe-ut"/><div className="stripe-uo"/>
      </div>
    </>
  );
}
