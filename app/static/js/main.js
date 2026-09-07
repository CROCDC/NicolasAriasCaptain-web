/**
 * Capitán Nicolás Arias — Main JavaScript
 *
 * The bar's stuck state, the full-screen index, smooth scrolling, the reveal,
 * the links that preselect the form, the form itself. No framework and no
 * dependencies: the whole file is DOM.
 */

/* =========================================================================
   1. UTILITIES
   ========================================================================= */

/**
 * Run `fn` at most once per `limit` ms.
 * @param {Function} fn
 * @param {number} limit
 * @returns {Function}
 */
function throttle(fn, limit) {
  let last = 0;
  return function (...args) {
    const now = Date.now();
    if (now - last >= limit) {
      last = now;
      fn.apply(this, args);
    }
  };
}

/** @returns {Element|null} */
function qs(selector, context = document) {
  return context.querySelector(selector);
}

/** @returns {NodeList} */
function qsa(selector, context = document) {
  return context.querySelectorAll(selector);
}

/** True when the visitor asked their system for less motion. */
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* =========================================================================
   2. THE BAR
   ========================================================================= */
(function initBar() {
  const bar = qs('#bar');
  if (!bar) return;

  const THRESHOLD = 40; // px scrolled before the bar takes a ground of its own

  function update() {
    bar.classList.toggle('stuck', window.scrollY > THRESHOLD);
  }

  requestAnimationFrame(update);
  window.addEventListener('scroll', throttle(update, 60), { passive: true });
})();

/* =========================================================================
   3. THE INDEX — one full-screen overlay, at every width
   ========================================================================= */
// There is no row of links in the bar to fall back on, so this has to work:
// focus is moved into the overlay, kept there while it is open, and handed
// back to the button that opened it.
(function initMenu() {
  const menu = qs('#menu');
  const openButton = qs('#menuOpen');
  const closeButton = qs('#menuClose');
  if (!menu || !openButton || !closeButton) return;

  const focusable = () => qsa('a[href], button', menu);

  function open() {
    menu.classList.add('open');
    menu.setAttribute('aria-hidden', 'false');
    openButton.setAttribute('aria-expanded', 'true');
    document.body.classList.add('menu-open');
    closeButton.focus();
  }

  function close({ restoreFocus = true } = {}) {
    menu.classList.remove('open');
    menu.setAttribute('aria-hidden', 'true');
    openButton.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('menu-open');
    if (restoreFocus) openButton.focus();
  }

  openButton.addEventListener('click', open);
  closeButton.addEventListener('click', () => close());

  // A section link closes the overlay and lets the smooth scroll take over,
  // so focus goes to the page rather than back to the button.
  qsa('.menu-link', menu).forEach((link) => {
    link.addEventListener('click', () => close({ restoreFocus: false }));
  });

  document.addEventListener('keydown', (event) => {
    if (!menu.classList.contains('open')) return;

    if (event.key === 'Escape') {
      close();
      return;
    }

    if (event.key !== 'Tab') return;

    const items = focusable();
    if (!items.length) return;

    const first = items[0];
    const last = items[items.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();

/* =========================================================================
   4. SMOOTH SCROLL
   ========================================================================= */
(function initSmoothScroll() {
  const BAR_OFFSET = 64; // the fixed bar's height

  document.addEventListener('click', (event) => {
    const anchor = event.target.closest('a[href^="#"]');
    if (!anchor) return;

    const targetId = anchor.getAttribute('href');
    if (!targetId || targetId === '#') return;

    const target = qs(targetId);
    if (!target) return;

    event.preventDefault();
    const top = target.getBoundingClientRect().top + window.scrollY - BAR_OFFSET;
    window.scrollTo({ top, behavior: REDUCED_MOTION ? 'auto' : 'smooth' });
  });
})();

/* =========================================================================
   5. REVEAL ON SCROLL
   ========================================================================= */
(function initReveal() {
  const elements = qsa('.reveal');
  if (!elements.length) return;

  // No IntersectionObserver, or no motion wanted: show everything at once
  // rather than leave the page blank.
  if (!('IntersectionObserver' in window) || REDUCED_MOTION) {
    elements.forEach((el) => el.classList.add('visible'));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -6% 0px' });

  elements.forEach((el) => observer.observe(el));
})();

/* =========================================================================
   6. THE GALLERY RAIL
   ========================================================================= */
// The rail scrolls natively; this only teaches it the arrow keys, because a
// horizontal scroller that a keyboard cannot move is a gallery some people
// simply cannot see.
(function initRail() {
  const rail = qs('#rail');
  if (!rail) return;

  rail.addEventListener('keydown', (event) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const step = rail.clientWidth * 0.6;
    rail.scrollBy({
      left: event.key === 'ArrowRight' ? step : -step,
      behavior: REDUCED_MOTION ? 'auto' : 'smooth',
    });
  });
})();

/* =========================================================================
   7. THE WHATSAPP TAB STANDS DOWN OVER THE FORM
   ========================================================================= */
// It is a shortcut to the same number the contact section prints in full, and
// at the height it floats it lands on top of the submit button on a phone.
// While that section is on screen it retires; everywhere else it is back.
(function initWaTab() {
  const tab = qs('.wa-tab');
  const contacto = qs('#contacto');
  if (!tab || !contacto || !('IntersectionObserver' in window)) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => tab.classList.toggle('wa-tab-away', entry.isIntersecting));
  }, { threshold: 0.12 });

  observer.observe(contacto);
})();

/* =========================================================================
   8. SERVICE LINKS PRESELECT THE FORM
   ========================================================================= */
// "Cotizar" under Traslados should land on a form that already says Traslado.
// Somebody who has to choose the service twice is somebody who half fills the
// form and leaves.
(function initServicePreselect() {
  const select = qs('#service_type');
  if (!select) return;

  qsa('[data-service]').forEach((link) => {
    link.addEventListener('click', () => {
      select.value = link.dataset.service;
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
})();

/* =========================================================================
   9. CONTACT FORM
   ========================================================================= */
(function initContactForm() {
  const form = qs('#contactForm');
  if (!form) return;

  const submitBtn = qs('#submitBtn', form);
  const btnText = qs('.btn-text', submitBtn);
  const successBox = qs('#formSuccess', form);
  const errorBox = qs('#formError', form);

  const FIELDS = {
    name: qs('#nameError', form),
    email: qs('#emailError', form),
    phone: qs('#phoneError', form),
    service_type: qs('#serviceError', form),
    message: qs('#messageError', form),
  };

  /** The control a message belongs to, so the field can be marked as well. */
  function controlFor(field) {
    return form.elements[field] || null;
  }

  /** Take one field out of the error state: the message and the red rule. */
  function clearField(field) {
    const message = FIELDS[field];
    if (message) message.textContent = '';
    const control = controlFor(field);
    if (control) {
      control.classList.remove('control-invalid');
      control.removeAttribute('aria-invalid');
    }
  }

  function clearErrors() {
    Object.keys(FIELDS).forEach(clearField);
    successBox.hidden = true;
    errorBox.hidden = true;
  }

  // A field that has been fixed stops looking wrong straight away, rather
  // than staying red until the next submit tells it otherwise.
  Object.keys(FIELDS).forEach((field) => {
    const control = controlFor(field);
    if (!control) return;
    const event = control.tagName === 'SELECT' ? 'change' : 'input';
    control.addEventListener(event, () => {
      if (control.classList.contains('control-invalid')) clearField(field);
    });
  });

  /**
   * Client-side check. The server validates the same things again — this only
   * saves a round trip, it is not what keeps bad data out.
   * @returns {Object<string,string>} field name -> message, empty when valid
   */
  function validate(data) {
    const errors = {};
    if (!data.name) errors.name = 'Escribí tu nombre.';
    if (!data.email) {
      errors.email = 'Escribí tu email.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
      errors.email = 'Ese email no parece válido.';
    }
    if (!data.service_type) errors.service_type = 'Elegí qué necesitás.';
    if (!data.message) errors.message = 'Contame un poco qué necesitás.';
    return errors;
  }

  /** Paint the messages, mark the controls, and put the caret in the first. */
  function showErrors(errors) {
    let firstControl = null;
    Object.entries(errors).forEach(([field, message]) => {
      const target = FIELDS[field];
      if (target) target.textContent = message;
      const control = controlFor(field);
      if (control) {
        control.classList.add('control-invalid');
        control.setAttribute('aria-invalid', 'true');
        if (!firstControl) firstControl = control;
      }
    });
    // Without this the button appears to do nothing: on a phone the first
    // message can be a screen and a half above the button that produced it.
    if (firstControl) firstControl.focus({ preventScroll: false });
  }

  function setBusy(busy) {
    submitBtn.disabled = busy;
    btnText.textContent = busy ? 'Enviando…' : 'Enviar consulta';
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearErrors();

    const data = {
      name: form.name.value.trim(),
      email: form.email.value.trim(),
      phone: form.phone.value.trim(),
      service_type: form.service_type.value,
      message: form.message.value.trim(),
    };

    const errors = validate(data);
    if (Object.keys(errors).length) {
      showErrors(errors);
      return;
    }

    setBusy(true);

    try {
      const response = await fetch('/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const payload = await response.json();

      if (response.ok && payload.success) {
        form.reset();
        successBox.textContent = payload.message;
        successBox.hidden = false;
      } else {
        errorBox.textContent = (payload.errors || []).join(' ')
          || 'No pude enviar el mensaje. Probá de nuevo o escribime por WhatsApp.';
        errorBox.hidden = false;
      }
    } catch (networkError) {
      errorBox.textContent =
        'No hay conexión con el servidor. Probá otra vez o escribime por WhatsApp.';
      errorBox.hidden = false;
    } finally {
      setBusy(false);
    }
  });
})();

/* =========================================================================
   10. FOOTER YEAR
   ========================================================================= */
(function initYear() {
  const target = qs('#currentYear');
  if (target) target.textContent = String(new Date().getFullYear());
})();
