// Single-colour line glyphs, one per region. Each glyph is decorative: the name is always written next to it.

const wrap = (body: string): string =>
  `<svg class="glyph" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;

export const GLYPHS: Record<string, string> = {
  // Vampire / Ghost (OB): wings or a sheet, the region that costs money and was never approved.
  OB: wrap(
    '<path d="M12 7c-1.5-2-4-2.5-6-1 1 1.2 1 2.6 0 4 2-.4 3.4.4 4 2 .6-1 1.2-1.5 2-1.5s1.4.5 2 1.5c.6-1.6 2-2.4 4-2-1-1.4-1-2.8 0-4-2-1.5-4.5-1-6 1z"/><path d="M10.5 14.5l1.5 2 1.5-2"/>',
  ),
  // Poltergeist (O): a small thrown object with motion lines.
  O: wrap('<circle cx="14" cy="10" r="4"/><path d="M3 9h5M4 13h4M5 17h4"/><path d="M14 14v5"/>'),
  // Phantom (B): a receipt with a hole where the item should be.
  B: wrap('<path d="M6 3h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5-2 1.5z"/><circle cx="12" cy="10" r="2.5" stroke-dasharray="2 1.6"/><path d="M9 15h6"/>'),
  // Skeleton (I): a key-shaped bone, declared but gone.
  I: wrap('<circle cx="7" cy="7" r="2.2"/><circle cx="7" cy="11" r="2.2"/><path d="M9 9h10"/><circle cx="19" cy="7" r="2.2"/><circle cx="19" cy="11" r="2.2"/>'),
  // Wraith (IB): a hooded outline paid for but unseen.
  IB: wrap('<path d="M6 21V11a6 6 0 0 1 12 0v10l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5z"/><path d="M9.5 11h.01M14.5 11h.01"/>'),
  // Familiar (IO): a cat's head, approved and present.
  IO: wrap('<path d="M5 20v-8l-1-7 4 3h8l4-3-1 7v8z"/><path d="M9.5 13h.01M14.5 13h.01M10.5 16.5h3"/>'),
  // Living (IOB): a lit candle.
  IOB: wrap('<path d="M9 21V11h6v10"/><path d="M12 8c-1.2-1.2-1-2.8 0-4 1 1.2 1.2 2.8 0 4z"/><path d="M7 21h10"/>'),
};
