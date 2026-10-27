// Generates simple placeholder PNG app icons for the Tauri build (no deps).
// A purple→teal diagonal gradient with a white "B". Replace later with real
// art via `npm run tauri icon <path-to-1024.png>`.
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'src-tauri', 'icons');
mkdirSync(OUT, { recursive: true });

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}
function chunk(type, data) {
  const t = Buffer.from(type, 'ascii');
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}

function makePNG(size) {
  // Build RGBA pixel buffer with a diagonal gradient + a rough "B" glyph.
  const px = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const t = (x + y) / (2 * size);
      // purple (124,58,237) → teal (6,182,212)
      const r = Math.round(124 + (6 - 124) * t);
      const g = Math.round(58 + (182 - 58) * t);
      const b = Math.round(237 + (212 - 237) * t);
      const i = (y * size + x) * 4;
      px[i] = r;
      px[i + 1] = g;
      px[i + 2] = b;
      px[i + 3] = 255;
    }
  }
  // crude white "B": two vertical+horizontal strokes in the central box
  const m = size;
  const inBglyph = (x, y) => {
    const lx = x / m, ly = y / m;
    if (lx < 0.32 || lx > 0.7 || ly < 0.26 || ly > 0.74) return false;
    const stem = lx < 0.4; // left vertical
    const bars =
      (ly > 0.26 && ly < 0.36) || // top
      (ly > 0.45 && ly < 0.55) || // middle
      (ly > 0.64 && ly < 0.74); // bottom
    const bowl = lx > 0.6 && lx < 0.7; // right edge
    return stem || bars || bowl;
  };
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      if (inBglyph(x, y)) {
        const i = (y * size + x) * 4;
        px[i] = 255;
        px[i + 1] = 255;
        px[i + 2] = 255;
      }
    }
  }
  // add filter byte (0) at the start of each scanline
  const raw = Buffer.alloc(size * (size * 4 + 1));
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0;
    px.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  const idat = deflateSync(raw);
  return Buffer.concat([
    sig,
    chunk('IHDR', ihdr),
    chunk('IDAT', idat),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const targets = [
  ['32x32.png', 32],
  ['128x128.png', 128],
  ['128x128@2x.png', 256],
  ['icon.png', 512],
  ['Square150x150Logo.png', 150],
  ['Square44x44Logo.png', 44],
  ['StoreLogo.png', 50],
];
for (const [name, size] of targets) {
  writeFileSync(join(OUT, name), makePNG(size));
  console.log('wrote', name, size);
}
console.log('Placeholder PNG icons generated in src-tauri/icons.');
console.log('For real icons + .ico/.icns, run: npm run tauri icon path/to/1024.png');
