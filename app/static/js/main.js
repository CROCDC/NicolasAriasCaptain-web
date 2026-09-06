/**
 * Capitán Nicolás Arias — Main JavaScript
 *
 * Navbar state, mobile menu, smooth scrolling, scroll reveal, hero parallax,
 * scroll spy, the service links that preselect the form, and the contact form
 * itself. No framework and no dependencies: everything here is a few dozen
 * lines of DOM.
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
   2. NAVBAR
   ========================================================================= */
(function initNavbar() {
  const navbar = qs('#navbar');
  if (!navbar) return;

  const THRESHOLD = 60; // px scrolled before the bar turns to paper

  function update() {
    navbar.classList.toggle('scrolled', window.scrollY > THRESHOLD);
  }

  requestAnimationFrame(update);
  window.addEventListener('scroll', throttle(update, 50), { passive: true });
})();

/* =========================================================================
   3. MOBILE MENU
   ========================================================================= */
(function initMobileMenu() {
  const hamburger = qs('#hamburger');
  const navLinks = qs('#navLinks');
  const overlay = qs('#mobileOverlay');
  if (!hamburger || !navLinks || !overlay) return;

  function open() {
    hamburger.classList.add('open');
    hamburger.setAttribute('aria-expanded', 'true');
    hamburger.setAttribute('aria-label', 'Cerrar menú');
    navLinks.classList.add('open');
    overlay.style.display = 'block';
    requestAnimationFrame(() => overlay.classList.add('visible'));
    document.body.style.overflow = 'hidden';
  }

  function close() {
    hamburger.classList.remove('open');
    hamburger.setAttribute('aria-expanded', 'false');
    hamburger.setAttribute('aria-label', 'Abrir menú');
    navLinks.classList.remove('open');
    overlay.classList.remove('visible');
    document.body.style.overflow = '';
    setTimeout(() => { overlay.style.display = 'none'; }, 400);
  }

  hamburger.addEventListener('click', () => {
    navLinks.classList.contains('open') ? close() : open();
  });

  overlay.addEventListener('click', close);

  qsa('.nav-link', navLinks).forEach((link) => link.addEventListener('click', close));

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && navLinks.classList.contains('open')) close();
  });
})();

/* =========================================================================
   4. SMOOTH SCROLL
   ========================================================================= */
(function initSmoothScroll() {
  const NAV_OFFSET = 78; // the fixed navbar's height

  document.addEventListener('click', (event) => {
    const anchor = event.target.closest('a[href^="#"]');
    if (!anchor) return;

    const targetId = anchor.getAttribute('href');
    if (!targetId || targetId === '#') return;

    const target = qs(targetId);
    if (!target) return;

    event.preventDefault();
    const top = target.getBoundingClientRect().top + window.scrollY - NAV_OFFSET;
    window.scrollTo({ top, behavior: REDUCED_MOTION ? 'auto' : 'smooth' });
  });
})();

/* =========================================================================
   5. SCROLL REVEAL
   ========================================================================= */
(function initScrollReveal() {
  const elements = qsa('.reveal');
  if (!elements.length) return;

  // No IntersectionObserver (or no motion wanted): show everything at once
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
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

  elements.forEach((el) => observer.observe(el));
})();

/* =========================================================================
   6. HERO PARALLAX
   ========================================================================= */
(function initParallax() {
  const heroBg = qs('#heroBg');
  if (!heroBg || REDUCED_MOTION) return;

  let ticking = false;

  function apply() {
    const scrolled = window.scrollY;
    if (scrolled < window.innerHeight) {
      heroBg.style.transform = `translate3d(0, ${scrolled * 0.35}px, 0)`;
    }
    ticking = false;
  }

  window.addEventListener('scroll', () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(apply);
  }, { passive: true });
})();

/* =========================================================================
   7. SCROLL SPY
   ========================================================================= */
(function initScrollSpy() {
  const sections = qsa('section[id], header[id]');
  const links = qsa('.nav-link');
  if (!sections.length || !links.length) return;

  const OFFSET = 140;

  function update() {
    const y = window.scrollY + OFFSET;
    let current = '';

    sections.forEach((section) => {
      if (y >= section.offsetTop && y < section.offsetTop + section.offsetHeight) {
        current = section.id;
      }
    });

    links.forEach((link) => {
      link.classList.toggle('active', link.getAttribute('href') === `#${current}`);
    });
  }

  requestAnimationFrame(update);
  window.addEventListener('scroll', throttle(update, 120), { passive: true });
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

  function clearErrors() {
    Object.values(FIELDS).forEach((el) => { if (el) el.textContent = ''; });
    successBox.hidden = true;
    errorBox.hidden = true;
  }

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

  function showErrors(errors) {
    Object.entries(errors).forEach(([field, message]) => {
      const target = FIELDS[field];
      if (target) target.textContent = message;
    });
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
