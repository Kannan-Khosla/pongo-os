import '@testing-library/jest-dom/vitest';

class IntersectionObserverMock {
  observe() {}
  disconnect() {}
  unobserve() {}
}

window.IntersectionObserver = IntersectionObserverMock;
window.matchMedia = window.matchMedia || (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || (() => {});
