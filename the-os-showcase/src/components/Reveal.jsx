import { useEffect, useRef } from 'react';

export default function Reveal({ as: Tag = 'div', className = '', children, delay = 0, ...props }) {
  const ref = useRef(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !('IntersectionObserver' in window)) {
      node.dataset.visible = 'true';
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      node.dataset.visible = 'true';
      observer.disconnect();
    }, { threshold: 0.12, rootMargin: '0px 0px -36px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return <Tag className={`reveal ${className}`.trim()} style={{ '--reveal-delay': `${delay}ms` }} ref={ref} {...props}>{children}</Tag>;
}
