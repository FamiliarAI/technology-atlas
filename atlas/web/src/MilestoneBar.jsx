const LABEL = { met: 'met', in_progress: 'in progress', none: 'no progress linked' };

export default function MilestoneBar({ status, labels, large }) {
  const descriptions = status.map((s, n) => `${labels?.[n] || `milestone ${n + 1}`} ${LABEL[s]}`);
  return (
    <div
      className={'bar' + (large ? ' large' : '')}
      role="img"
      aria-label={descriptions.join(', ')}
    >
      {status.map((s, n) => <i
        key={n}
        className={'seg ' + s}
        title={labels?.[n] ? descriptions[n] : undefined}
      />)}
    </div>
  );
}
