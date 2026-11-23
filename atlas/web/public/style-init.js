// Paper is the default look; ?style=sky (kept for the tab's session) shows the dark sky. Set
// before the stylesheet paints, so a page never flashes the other style; src/style.js repeats
// this once the app runs. Share cards (/share/...) keep the sky.
(function () {
  var paper = true;
  try {
    var asked = new URLSearchParams(location.search).get('style');
    if (asked) sessionStorage.setItem('atlas-style', asked);
    paper = (asked || sessionStorage.getItem('atlas-style')) !== 'sky';
  } catch (e) {}
  if (location.pathname.indexOf('/share/') === 0) paper = false;
  if (paper) document.documentElement.className += ' paper';
})();
