(function () {
  document.documentElement.classList.add('js');
  var BASE = (document.currentScript && document.currentScript.src || '').replace(/assets\/app\.js.*$/, '');
  // ---------- Navegación: scroll suave y sección activa
  var header = document.querySelector('.top');
  var links = Array.prototype.slice.call(document.querySelectorAll('.nav a'));
  function goTo(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var y = el.getBoundingClientRect().top + window.pageYOffset - header.offsetHeight + 1;
    window.scrollTo({ top: y, behavior: 'smooth' });
    document.body.classList.remove('nav-open');
  }
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest('a[href^="#"]');
    if (!a) return;
    var id = a.getAttribute('href').slice(1);
    if (!id || !document.getElementById(id)) return;
    ev.preventDefault();
    if (a.dataset.tipo) setTipo(a.dataset.tipo);
    goTo(id);
    if (history.replaceState) history.replaceState(null, '', '#' + id);
  });
  var menuBtn = document.querySelector('.menu');
  if (menuBtn) menuBtn.addEventListener('click', function () {
    document.body.classList.toggle('nav-open');
    this.setAttribute('aria-expanded', document.body.classList.contains('nav-open'));
  });
  function onScroll() {
    var y = window.pageYOffset + header.offsetHeight + window.innerHeight * 0.3, cur = '';
    ['episodios', 'preguntas', 'proponer', 'sobre', 'sobre-mi'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el && el.offsetTop <= y) cur = id;
    });
    if (cur && window.innerHeight + window.pageYOffset >= document.body.scrollHeight - 4) cur = 'sobre-mi';
    links.forEach(function (l) { l.classList.toggle('on', l.dataset.sec === cur); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ---------- Vídeo de YouTube ligero
  document.querySelectorAll('.lite-yt').forEach(function (b) {
    b.addEventListener('click', function () {
      // Abierto como archivo local (vista previa) YouTube no deja incrustar: se abre en YouTube
      if (b.querySelector('iframe')) return;
      if (location.protocol === 'file:') { window.open('https://www.youtube.com/watch?v=' + b.dataset.id, '_blank'); return; }
      var f = document.createElement('iframe');
      f.referrerPolicy = 'strict-origin-when-cross-origin';
      f.src = 'https://www.youtube-nocookie.com/embed/' + b.dataset.id + '?autoplay=1&rel=0';
      f.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
      f.title = 'Episodio en YouTube';
      b.innerHTML = ''; b.appendChild(f); b.style.cursor = 'default';
    });
  });

  // ---------- Buscador + filtros por tema (+ búsqueda dentro de las transcripciones)
  var q = document.getElementById('q');
  if (q) {
    var cards = Array.prototype.slice.call(document.querySelectorAll('#grid .card'));
    var empty = document.getElementById('empty'), deep = document.getElementById('deep');
    var norm = function (s) { return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); };
    cards.forEach(function (c) { c._s = norm(c.dataset.search || ''); });
    var grid = document.getElementById('grid'), more = document.getElementById('more');
    var filtro = '', IDX = null, loading = false;
    function expand() { grid.classList.remove('collapsed'); more.parentNode.hidden = true; }
    more.addEventListener('click', expand);
    function apply() {
      var words = norm(q.value.trim()).split(/\s+/).filter(Boolean), n = 0, viaDeep = false;
      if (words.length || filtro) expand();
      if (words.length && words.join('').length >= 3 && !IDX && !loading) {
        loading = true;
        fetch(BASE + 'assets/busqueda.json').then(function (r) { return r.json(); })
          .then(function (d) { IDX = d; apply(); }).catch(function () {});
      }
      cards.forEach(function (c) {
        var okF = !filtro || c.dataset.sector === filtro;
        var okQ = words.every(function (w) { return c._s.indexOf(w) > -1; });
        if (!okQ && IDX && IDX[c.dataset.slug]) {
          var t = ' ' + IDX[c.dataset.slug] + ' ';
          okQ = words.every(function (w) { return t.indexOf(' ' + w) > -1; });
          if (okQ) viaDeep = true;
        }
        var ok = okF && (!words.length || okQ);
        c.hidden = !ok; if (ok) n++;
      });
      empty.hidden = n > 0;
      deep.hidden = !viaDeep;
    }
    q.addEventListener('input', apply);
    document.querySelectorAll('.fchip').forEach(function (b) {
      b.addEventListener('click', function () {
        document.querySelectorAll('.fchip').forEach(function (x) { x.classList.toggle('on', x === b); x.setAttribute('aria-pressed', x === b); });
        filtro = b.dataset.f; apply();
      });
    });
  }

  // ---------- Animación suave al aparecer
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -40px 0px' });
    document.querySelectorAll('.reveal').forEach(function (el) { io.observe(el); });
  } else { document.querySelectorAll('.reveal').forEach(function (el) { el.classList.add('in'); }); }

  // ---------- Selector de plataforma
  var dataEl = document.getElementById('ep-data');
  var modal = document.getElementById('modal');
  if (dataEl && modal) {
    var D = JSON.parse(dataEl.textContent), lastBtn = null;
    var $ = function (id) { return document.getElementById(id); };
    function open(key) {
      var e = D.eps[key]; if (!e) return;
      $('m-img').src = e.img; $('m-num').textContent = e.num ? 'Episodio ' + e.num : '';
      $('m-guest').textContent = e.guest; $('m-role').textContent = e.role; $('m-meta').textContent = e.meta;
      $('m-links').innerHTML = e.links.map(function (l) {
        return '<a class="m-link" href="' + l.url + '" target="_blank" rel="noopener">' + (D.icons[l.id] || '') +
          '<span>' + l.name + '</span></a>';
      }).join('');
      $('m-more').href = e.page;
      modal.hidden = false; document.body.classList.add('modal-open');
      modal.querySelector('.modal-x').focus();
    }
    function close() {
      modal.hidden = true; document.body.classList.remove('modal-open');
      if (lastBtn) lastBtn.focus();
    }
    document.addEventListener('click', function (ev) {
      var b = ev.target.closest('.card-btn'); if (!b || !D.eps[b.dataset.ep]) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
      ev.preventDefault(); lastBtn = b; open(b.dataset.ep);
    });
    modal.addEventListener('click', function (ev) { if (ev.target.hasAttribute('data-close')) close(); });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && !modal.hidden) close(); });
  }

  // ---------- Formularios (se envían a Google Forms)
  function setTipo() {}
  function sendForm(form, btn, thanks, label, prep) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (prep) prep();
      btn.disabled = true; btn.textContent = 'Enviando…';
      var body = new URLSearchParams(new FormData(form));
      fetch(form.dataset.action, { method: 'POST', mode: 'no-cors', body: body })
        .then(function () { form.hidden = true; thanks.hidden = false; })
        .catch(function () {
          btn.disabled = false; btn.textContent = label;
          var p = document.createElement('p'); p.className = 'form-err';
          p.textContent = 'No se ha podido enviar. Inténtalo de nuevo en un momento.'; form.appendChild(p);
        });
    });
  }
  var form = document.getElementById('qform');
  if (form) {
    var anon = document.getElementById('anon'), nombre = document.getElementById('nombre');
    anon.addEventListener('change', function () {
      document.getElementById('name-label').hidden = anon.checked;
      nombre.required = !anon.checked;
      document.getElementById('consent').textContent = anon.checked
        ? 'Acepto que mi pregunta aparezca en esta web y se lea en el pódcast (sin mi nombre).'
        : 'Acepto que mi pregunta y mi nombre aparezcan en esta web y se lean en el pódcast.';
    });
    sendForm(form, document.getElementById('qsend'), document.getElementById('thanks'), 'Enviar pregunta',
      function () { if (anon.checked) nombre.value = 'Anónimo'; });
  }
  var pform = document.getElementById('pform');
  if (pform) {
    var v = function (id) { return (document.getElementById(id).value || '').trim(); };
    sendForm(pform, document.getElementById('psend'), document.getElementById('pthanks'), 'Enviar propuesta', function () {
      document.getElementById('pmsg').value =
        'Propuesto: ' + v('p-quien') + '\nA qué se dedica: ' + v('p-rol') + '\nContacto: ' + v('p-contacto') +
        (v('p-porque') ? '\nPor qué: ' + v('p-porque') : '') + (v('p-mail') ? '\nCorreo de quien propone: ' + v('p-mail') : '');
    });
  }

  // ---------- Muro de preguntas publicadas (hoja de Google publicada en CSV)
  var muro = document.getElementById('muro');
  function parseCSV(t) {
    var rows = [], row = [], f = '', q = false;
    for (var i = 0; i < t.length; i++) {
      var c = t[i];
      if (q) { if (c === '"') { if (t[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c; }
      else if (c === '"') q = true;
      else if (c === ',') { row.push(f); f = ''; }
      else if (c === '\n' || c === '\r') { if (c === '\r' && t[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = ''; }
      else f += c;
    }
    if (f || row.length) { row.push(f); rows.push(row); }
    return rows;
  }
  var MES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  function fecha(s) { var m = (s || '').match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/); return m ? +m[1] + ' ' + MES[+m[2] - 1] + ' ' + m[3] : ''; }
  function esc(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
  if (muro && muro.dataset.csv) {
    fetch(muro.dataset.csv + (muro.dataset.csv.indexOf('?') > -1 ? '&' : '?') + 't=' + Date.now())
      .then(function (r) { return r.text(); })
      .then(function (t) {
        var rows = parseCSV(t).slice(1).filter(function (r) { return r[3] && r[3].trim() && !/propuesta/i.test(r[1] || ''); });
        if (!rows.length) return;
        document.getElementById('muro-list').innerHTML = rows.map(function (r) {
          var tipo = r[1] && r[1] !== 'Pregunta' ? '<span class="q-tag">' + esc(r[1]) + '</span>' : '';
          var resp = r[4] && r[4].trim() ? '<span class="q-done">Respondida en el episodio ' + esc(r[4].replace(/^\D*/, '#')) + '</span>' : '';
          return '<article class="q">' + tipo + '<p class="q-msg">' + esc(r[3]) + '</p><p class="q-meta"><strong>' + esc(r[2]) + '</strong> · ' + fecha(r[0]) + '</p>' + resp + '</article>';
        }).join('');
        muro.hidden = false;
      }).catch(function () {});
  }

  if (location.hash && location.hash.length > 1) setTimeout(function () { goTo(location.hash.slice(1)); }, 200);
})();
