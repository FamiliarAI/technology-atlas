// The site's look. Paper (a light editorial document) is the default; ?style=sky shows the older
// dark style, kept for the tab's session, and ?style=paper goes back.
export function paperChosen() {
  try {
    const asked = new URLSearchParams(window.location.search).get('style');
    if (asked) sessionStorage.setItem('atlas-style', asked);
    return (asked || sessionStorage.getItem('atlas-style')) !== 'sky';
  } catch {
    return true;
  }
}

// Sets the class on <html> that every paper rule hangs from.
// Share cards (/share/...) are images drawn in the sky style, so they stay dark.
export function applyStyle() {
  const paper = paperChosen() && !window.location.pathname.startsWith('/share/');
  document.documentElement.classList.toggle('paper', paper);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', paper ? '#fbfaf7' : '#05070d');
  return paper;
}

// Read at draw time by colours set in code (star fills), which CSS cannot reach.
export const onPaper = () => typeof document !== 'undefined' && document.documentElement.classList.contains('paper');
