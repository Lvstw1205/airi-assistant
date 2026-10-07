// Opening index.html from Finder should reach the running application.
if (window.location.protocol === 'file:') {
  window.location.replace('http://127.0.0.1:8765/');
}
