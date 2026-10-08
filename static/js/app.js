(function () {
  var root = document.documentElement;
  var tbtn = document.getElementById('theme-toggle');
  function syncThemeIcon() {
    if (!tbtn) return;
    var dark = root.getAttribute('data-theme') === 'dark';
    tbtn.firstElementChild.textContent = dark ? '\u2600' : '\u263E';   // sun in dark mode, moon in light mode
    var label = dark ? 'Switch to light mode' : 'Switch to dark mode';
    tbtn.setAttribute('aria-label', label); tbtn.setAttribute('title', label);
  }
  if (tbtn) {
    syncThemeIcon();
    tbtn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
      syncThemeIcon();
      if (window.renderCharts) window.renderCharts();
    });
  }
  var nt = document.getElementById('nav-toggle');
  if (nt) {
    var inner = nt.closest('.navbar-inner');
    nt.addEventListener('click', function () {
      var open = inner.classList.toggle('open');
      nt.setAttribute('aria-expanded', open ? 'true' : 'false');
      nt.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && inner.classList.contains('open')) { inner.classList.remove('open'); nt.setAttribute('aria-expanded', 'false'); nt.focus(); }
    });
  }
  // confirmation prompts for destructive forms
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!window.confirm(f.getAttribute('data-confirm'))) e.preventDefault(); });
  });
  // loading state + client-side validation feedback (server validation is authoritative)
  document.querySelectorAll('form[data-loading]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (!f.checkValidity()) { e.preventDefault(); f.reportValidity(); return; }
      var b = e.submitter || f.querySelector('button[type=submit]');
      if (b) { b.disabled = true; b.setAttribute('data-label', b.textContent); b.textContent = f.getAttribute('data-loading'); }
      // keep the chosen mode value in the request even though the button is disabled
      if (e.submitter && e.submitter.name) {
        var h = document.createElement('input'); h.type = 'hidden'; h.name = e.submitter.name; h.value = e.submitter.value; f.appendChild(h);
      }
    });
  });
  // client-side file checks for the CSV upload
  var file = document.querySelector('input[type=file]');
  if (file) file.addEventListener('change', function () {
    var f = file.files[0]; if (!f) return;
    var msg = '';
    if (!/\.csv$/i.test(f.name)) msg = 'Please choose a .csv file.';
    else if (f.size > 5 * 1024 * 1024) msg = 'This file is larger than 5 MB.';
    file.setCustomValidity(msg); if (msg) file.reportValidity();
  });
})();
