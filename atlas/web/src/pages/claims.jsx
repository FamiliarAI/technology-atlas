import { StatusMark } from '../glyphs.jsx';

const done = (item) => item.status.length > 0 && item.met === item.status.length;

// "B needs A first" is falsified once B is achieved while A is not.
export const claimState = (a, b) => (done(b) && !done(a) ? 'falsified' : 'standing');

export function ClaimStatus({ state }) {
  return (
    <span className={'claim-status ' + state}>
      {state === 'falsified' ? (
        <svg width="14" height="14" viewBox="-8 -8 16 16" aria-hidden="true">
          <path d="M-5 -5L5 5M5 -5L-5 5" />
        </svg>
      ) : (
        <StatusMark status="none" />
      )}
      {state === 'falsified' ? 'Falsified' : 'Standing'}
    </span>
  );
}
