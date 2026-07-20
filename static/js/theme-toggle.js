/**
 * 主题切换：暗色 / 浅色（qsmile 风格）
 * 优先读取 localStorage，默认暗色
 */
(function () {
  var KEY = 'erp-theme';
  var root = document.documentElement;

  function apply(theme) {
    if (theme !== 'light' && theme !== 'dark') {
      theme = 'dark';
    }
    root.setAttribute('data-theme', theme);
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) {}
    syncButtons(theme);
  }

  function current() {
    return root.getAttribute('data-theme') || 'dark';
  }

  function toggle() {
    apply(current() === 'dark' ? 'light' : 'dark');
  }

  function syncButtons(theme) {
    var nodes = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < nodes.length; i++) {
      var btn = nodes[i];
      var isDark = theme === 'dark';
      btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      btn.setAttribute('title', isDark ? '切换到浅色模式' : '切换到暗色模式');
      var label = btn.querySelector('[data-theme-label]');
      if (label) {
        label.textContent = isDark ? '暗色模式' : '浅色模式';
      }
    }
  }

  // 尽早应用，减少闪烁（也可由 head 内联脚本先执行）
  try {
    apply(localStorage.getItem(KEY) || 'dark');
  } catch (e) {
    apply('dark');
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-theme-toggle]');
    if (btn) {
      e.preventDefault();
      toggle();
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    syncButtons(current());
  });

  window.ERPTheme = { apply: apply, toggle: toggle, current: current };
})();
