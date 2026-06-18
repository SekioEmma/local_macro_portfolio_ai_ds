import { useLayoutEffect } from "react";

export function useBodyScrollLock() {
  useLayoutEffect(() => {
    const body = document.body;
    const root = document.documentElement;
    const scrollY = window.scrollY;
    const scrollbarGap = Math.max(0, window.innerWidth - root.clientWidth);
    const bodyPaddingRight =
      Number.parseFloat(window.getComputedStyle(body).paddingRight) || 0;
    const previousBodyStyles = {
      overflow: body.style.overflow,
      paddingRight: body.style.paddingRight,
      position: body.style.position,
      top: body.style.top,
      width: body.style.width
    };
    const previousRootOverscroll = root.style.overscrollBehavior;

    body.style.overflow = "hidden";
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.width = "100%";
    if (scrollbarGap > 0) {
      body.style.paddingRight = `${bodyPaddingRight + scrollbarGap}px`;
    }
    root.style.overscrollBehavior = "none";

    return () => {
      body.style.overflow = previousBodyStyles.overflow;
      body.style.paddingRight = previousBodyStyles.paddingRight;
      body.style.position = previousBodyStyles.position;
      body.style.top = previousBodyStyles.top;
      body.style.width = previousBodyStyles.width;
      root.style.overscrollBehavior = previousRootOverscroll;
      window.scrollTo(0, scrollY);
    };
  }, []);
}
