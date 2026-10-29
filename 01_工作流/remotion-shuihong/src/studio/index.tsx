import React from 'react';
import {Composition, registerRoot, staticFile} from 'remotion';
import {EpisodeView} from './Episode';
import type {Episode} from './types';

// History Studio entry. Each episode is staged into its own public dir by
// `studio.py build`; render with `--public-dir <stage>/public`.
// The composition reads public/episode.json, so no episode is hard-coded here.

type Props = {episode: Episode | null; mapOnly?: boolean};

const Root: React.FC = () => (
  <Composition
    id="Episode"
    component={EpisodeView}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={300}
    defaultProps={{episode: null} as Props}
    calculateMetadata={async ({props}) => {
      const episode: Episode = props.episode ?? (await fetch(staticFile('episode.json')).then((r) => r.json()));
      return {
        props: {...props, episode},
        fps: episode.fps,
        width: episode.width,
        height: episode.height,
        durationInFrames: Math.round(episode.duration * episode.fps),
      };
    }}
  />
);

registerRoot(Root);
