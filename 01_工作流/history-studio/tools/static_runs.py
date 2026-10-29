"""Find long stretches with no new motion in an episode's latest build (交付前自查第 7 项).

A beat is "quiet" when no element starts in it (cities, regions, camps, trails and the dialogue stage don't
count as motion), the camera has no keyframe in it, and it is not on a dialogue stage. Runs of quiet beats
of 5 s or more are listed: give them motion, a deployment diagram (`tactic`) or an illustration window
(`vignette`).

    python tools/static_runs.py 17          # one episode
    python tools/static_runs.py 16 29       # a range
"""
import glob
import json
import os
import sys

STUDIO = os.path.join(os.path.dirname(__file__), '..', '..', '..', '05_项目', 'Remotion', 'studio')
PASSIVE = {'city', 'region', 'camp', 'trail', 'stage', 'breathe', 'faction_bar', 'legend'}
MIN_RUN = 5.0


def runs(ep):
    starts = sorted(e['start'] for e in ep['elements'] if e['type'] not in PASSIVE and e.get('start') is not None)
    cams = sorted(k['t'] for k in ep.get('camera', []) if 't' in k)
    stages = [(e['start'], e['end']) for e in ep['elements'] if e['type'] == 'stage']
    busy = lambda a, z: any(a <= s < z for s in starts) or any(a <= c < z for c in cams)
    on_stage = lambda t: any(a <= t < z for a, z in stages)
    out, run = [], []
    for s in ep['segments'] + [None]:
        if s is not None and not busy(s['start'], s['end']) and not on_stage((s['start'] + s['end']) / 2):
            run.append(s)
            continue
        if run and run[-1]['end'] - run[0]['start'] >= MIN_RUN:
            out.append(run)
        run = []
    return out


def main(first, last):
    for n in range(first, last + 1):
        dirs = glob.glob(os.path.join(STUDIO, f's01e{n:02d}-*'))
        builds = [b for d in dirs for b in glob.glob(os.path.join(d, '*')) if os.path.isfile(os.path.join(b, 'public', 'episode.json'))]
        if not builds:
            continue
        b = max(builds, key=os.path.getmtime)
        ep = json.load(open(os.path.join(b, 'public', 'episode.json'), encoding='utf-8'))
        found = runs(ep)
        print(f"== ep{n:02d} {os.path.basename(os.path.dirname(b))} {os.path.basename(b)} ({ep['duration']:.0f}s): "
              + (f'{len(found)} 段静止 ≥{MIN_RUN:.0f}s' if found else '没有长时间静止'))
        for r in found:
            print(f"   {r[0]['start']:6.1f}–{r[-1]['end']:6.1f}s ({r[-1]['end'] - r[0]['start']:4.1f}s) "
                  + ' | '.join(f"{x['id']}:{x['text'][:24]}" for x in r))


if __name__ == '__main__':
    a = [int(x) for x in sys.argv[1:]] or [1]
    main(a[0], a[-1])
