const LABEL = { met: 'met', in_progress: 'in progress', none: 'no progress linked' };

export default function MilestoneBar({ status, large }) {
  return (
    <div className={'bar' + (large ? ' large' : '')} role="img" aria-label={status.map((s, n) => `milestone ${n + 1} ${LABEL[s]}`).join(', ')}>
      {status.map((s, n) => <i key={n} className={'seg ' + s} />)}
    </div>
  );
}
