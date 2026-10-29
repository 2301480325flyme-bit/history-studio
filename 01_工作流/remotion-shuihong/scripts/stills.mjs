// Render many stills of one staged episode with a single bundle (review sheets, cover backgrounds).
// usage: node scripts/stills.mjs <public-dir> <out-dir> <frames: 120,450,900> [--scale=0.5] [--map-only]
// Files are written as <out-dir>/f<frame>.jpg (or .png with --png).
import path from 'node:path';
import fs from 'node:fs';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';

const [publicDir, outDir, framesArg, ...rest] = process.argv.slice(2);
if (!publicDir || !outDir || !framesArg) {
  console.error('usage: node scripts/stills.mjs <public-dir> <out-dir> <frames> [--scale=0.5] [--map-only] [--png]');
  process.exit(2);
}
const opt = Object.fromEntries(rest.map((a) => a.replace(/^--/, '').split('=')).map(([k, v]) => [k, v ?? true]));
const scale = Number(opt.scale ?? 0.5);
const ext = opt.png ? 'png' : 'jpeg';
const frames = framesArg.split(',').map(Number).filter((n) => Number.isFinite(n));
fs.mkdirSync(outDir, {recursive: true});

const serveUrl = await bundle({entryPoint: path.resolve('src/studio/index.tsx'), publicDir: path.resolve(publicDir)});
const inputProps = {episode: null, mapOnly: Boolean(opt['map-only'])};
const composition = await selectComposition({serveUrl, id: 'Episode', inputProps});
for (const frame of frames) {
  const f = Math.max(0, Math.min(composition.durationInFrames - 1, frame));
  const output = path.join(outDir, `f${frame}.${ext === 'jpeg' ? 'jpg' : 'png'}`);
  await renderStill({composition, serveUrl, output, frame: f, inputProps, scale, imageFormat: ext, ...(ext === 'jpeg' ? {jpegQuality: 88} : {})});
  console.log(output);
}
