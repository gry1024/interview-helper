# 前端设计系统 · Apple 极简

> 把这套变量复制到 `index.html` 顶部，整个站点立刻进入"Apple 极简"调性。
> 本文档不含任何产品业务内容，纯设计资产。

---

## 0. 一句话设计哲学

> **极淡冷灰作背景，深炭黑作正文，细横线代替卡片边框；大量留白、克制的微圆角、几乎无阴影。**
> **强调色（蓝）只在关键行动点出现，其他所有按钮都用中性色。**

**它是**：纯白/极淡灰背景 · 细横线分割模块 · 微圆角（4-6px） · 极淡阴影 · 衬线主标 + 无衬线辅助。
**它不是**：Material 卡片阴影 · 彩色块 · 渐变背景 · 16px+ 大圆角胶囊。

---

## 1. CSS 变量（一键复制）

```css
:root{
  /* 背景 */
  --bg:#F5F5F7;
  --bg-elevated:#FFFFFF;
  --bg-hover:#EBEBEE;

  /* 文字 */
  --fg:#1D1D1F;
  --fg-secondary:#6E6E73;
  --fg-tertiary:#86868B;

  /* 强调色：克制 */
  --accent:#1D1D1F;
  --accent-blue:#0071E3;

  /* 主按钮 */
  --btn-primary-bg:#1D1D1F;
  --btn-primary-hover:#000000;

  /* 分割线 */
  --divider:#D2D2D7;
  --divider-subtle:#E8E8ED;

  /* 状态色（降低饱和度） */
  --danger:#FF3B30;
  --success:#34C759;
  --warning:#FF9500;

  /* 圆角 */
  --radius:6px;
  --radius-sm:4px;
  --radius-pill:999px;

  /* 阴影：极淡或不要 */
  --shadow-subtle:0 1px 2px rgba(0,0,0,0.03);
  --shadow-pop:0 4px 24px rgba(0,0,0,0.08);
  --shadow-fab:0 2px 12px rgba(0,0,0,0.18);

  /* 字体 */
  --font-serif:"Noto Serif SC","Source Han Serif SC","Songti SC",serif;
  --font-sans:-apple-system,BlinkMacSystemFont,"SF Pro Display","PingFang SC","Noto Sans SC",sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;

  /* 基础字号 */
  --fs-base:15px;

  /* 缓动 */
  --ease-apple:cubic-bezier(.2,.7,.2,1);
}

[data-theme="dark"]{
  --bg:#1A1A1C;
  --bg-elevated:#242426;
  --bg-hover:#2C2C2E;
  --fg:#F5F5F7;
  --fg-secondary:#AEAEB2;
  --fg-tertiary:#8E8E93;
  --accent:#F5F5F7;
  --accent-blue:#0A84FF;
  --btn-primary-bg:#48484A;
  --btn-primary-hover:#5C5C5E;
  --divider:#38383A;
  --divider-subtle:#2C2C2E;
  --shadow-pop:0 4px 24px rgba(0,0,0,0.4);
}

/* 基础重置 */
*{ box-sizing:border-box; margin:0; padding:0; }
html{ font-size:var(--fs-base, 15px); }
html, body{ height:100%; }
body{
  font-family:var(--font-serif);
  background:var(--bg);
  color:var(--fg);
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  line-height:1.7;
  font-size:1rem;
  letter-spacing:0.01em;
}
a{ color:var(--accent-blue); text-decoration:none; transition:opacity .15s; }
a:hover{ opacity:0.7; }
button{ font-family:inherit; cursor:pointer; border:none; background:none; color:inherit; }
input, select, textarea{ font-family:var(--font-sans); color:inherit; }
::selection{ background:#0071E3; color:#fff; opacity:0.15; }
```

---

## 2. 使用规则

| 用途 | 颜色 |
|------|------|
| 正文 | `var(--fg)` |
| 次要文字 | `var(--fg-secondary)` |
| 标签/辅助 | `var(--fg-tertiary)` |
| 主按钮 | `var(--btn-primary-bg)` + 白字 |
| 关键 CTA / 链接 | `var(--accent-blue)` |
| 危险 | `var(--danger)` |
| 分割线 | `var(--divider-subtle)` |

**铁律**：
- 蓝色**只在关键行动点**（链接、主 CTA），装饰性元素绝不用蓝
- 大块背景绝不用渐变
- icon 用 `var(--fg-secondary)` 或 `var(--fg-tertiary)`
- 模块间垂直间距 ≥ 48px（Apple 风格灵魂）

---

## 3. 组件库（13 个核心组件）

### 按钮

```css
.btn{
  display:inline-flex; align-items:center; justify-content:center; gap:6px;
  padding:9px 24px; border-radius:var(--radius-sm);
  font-size:0.933rem; font-weight:400;
  border:1px solid var(--divider);
  background:var(--bg-elevated); color:var(--fg);
  transition:background .2s, border-color .2s, opacity .15s;
  font-family:var(--font-sans); cursor:pointer;
}
.btn:hover{ background:var(--bg-hover); }
.btn:disabled{ opacity:.5; cursor:not-allowed; }
.btn-primary{ background:var(--btn-primary-bg); color:#fff; border:none; }
.btn-primary:hover{ background:var(--btn-primary-hover); opacity:0.88; }
.btn-danger{ background:var(--danger); color:#fff; border-color:var(--danger); }
.btn-sm{ padding:5px 12px; font-size:0.8rem; }
```

### 输入框

```css
.input{
  background:var(--bg-elevated);
  border:1px solid var(--divider);
  border-radius:var(--radius-sm);
  padding:8px 12px;
  font-size:0.933rem; color:var(--fg);
  outline:none; line-height:22px;
  font-family:var(--font-sans);
  transition:border-color .2s, box-shadow .2s;
}
.input:focus{
  border-color:var(--accent-blue);
  box-shadow:0 0 0 3px rgba(0,113,227,0.12);
}
.input::placeholder{ color:var(--fg-tertiary); }
```

### 卡片 · **打破卡片**

```css
/* ❌ 不要传统卡片 */
/* .card{ background:white; border:1px solid #eee; border-radius:8px; box-shadow:...; } */

/* ✅ 用细横线分隔 */
.divider-section{
  padding:24px 0;
  border-bottom:1px solid var(--divider-subtle);
}
.divider-section:last-child{ border-bottom:none; }
```

### 导航栏（毛玻璃）

```css
.header{
  background:rgba(255,255,255,0.72);
  backdrop-filter:saturate(180%) blur(20px);
  -webkit-backdrop-filter:saturate(180%) blur(20px);
  border-bottom:1px solid var(--divider-subtle);
  position:sticky; top:0; z-index:100;
}
[data-theme="dark"] .header{ background:rgba(26,26,28,0.72); }

.header-inner{
  max-width:1024px; margin:0 auto;
  display:flex; align-items:center; gap:32px;
  padding:16px 24px;
}
.tab-btn{
  padding:4px 0; font-size:0.933rem; font-weight:400;
  color:var(--fg-secondary); background:none;
  border-bottom:1.5px solid transparent;
  transition:color .2s, border-color .2s;
  font-family:var(--font-serif); cursor:pointer;
}
.tab-btn:hover{ color:var(--fg); }
.tab-btn.active{ color:var(--fg); font-weight:500; border-bottom-color:var(--fg); }
```

### 统计卡片（横排通栏）

```css
.stats-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));
  gap:0;
  border-top:1px solid var(--divider-subtle);
  border-bottom:1px solid var(--divider-subtle);
}
.stat-card{
  background:none; border:none;
  padding:16px 18px;
  border-right:1px solid var(--divider-subtle);
}
.stat-card:last-child{ border-right:none; }
.stat-card .stat-label{ font-size:0.8rem; color:var(--fg-secondary); letter-spacing:0.04em; }
.stat-card .stat-value{
  font-size:1.867rem; font-weight:400;
  margin-top:6px; line-height:1.1;
  font-variant-numeric:tabular-nums;
  letter-spacing:-0.03em; font-family:var(--font-serif);
}
```

### 列表项

```css
.list-item{
  padding:20px 20px;
  border-bottom:1px solid var(--divider-subtle);
  cursor:pointer;
  transition:background .2s;
}
.list-item:hover{ background:var(--bg-hover); }
.list-item:last-child{ border-bottom:none; }
```

### Toast / Flash

```css
.flash{
  display:flex; align-items:center; gap:10px;
  padding:12px 20px; border-radius:var(--radius);
  background:rgba(255,255,255,0.9);
  backdrop-filter:blur(20px);
  border:1px solid var(--divider);
  box-shadow:0 2px 12px rgba(0,0,0,0.06);
  font-family:var(--font-sans);
}
.flash.error{ border-left:3px solid var(--danger); }
.flash.success{ border-left:3px solid var(--success); }
.flash.info{ border-left:3px solid var(--accent-blue); }

.toast{
  position:fixed; left:50%; bottom:80px;
  transform:translateX(-50%);
  background:rgba(29,29,31,0.92); color:#fff;
  padding:11px 22px; border-radius:20px;
  font-size:0.867rem;
  backdrop-filter:blur(10px);
  font-family:var(--font-sans);
}
```

### FAB 浮按钮

```css
.fab{
  position:fixed; right:28px; bottom:28px;
  width:44px; height:44px; border-radius:50%;
  background:var(--btn-primary-bg); color:#fff;
  display:flex; align-items:center; justify-content:center;
  box-shadow:var(--shadow-fab);
  cursor:pointer; z-index:200;
  transition:transform .2s, box-shadow .2s;
  opacity:0.88;
}
.fab:hover{ transform:translateY(-2px); background:var(--btn-primary-hover); }
```

### Spinner

```css
.spinner{
  display:inline-block; width:16px; height:16px;
  border:2px solid var(--divider-subtle);
  border-top-color:var(--fg-secondary);
  border-radius:50%;
  animation:spin .7s linear infinite;
}
@keyframes spin{ to{ transform:rotate(360deg); } }
```

### 空状态

```css
.empty-state{
  text-align:center; padding:64px 24px;
  color:var(--fg-secondary); font-weight:300;
}
.empty-state svg{ width:32px; height:32px; color:var(--fg-tertiary); margin-bottom:12px; }
```

### Badge

```css
.badge{
  font-size:0.733rem; font-weight:400;
  padding:3px 10px; border-radius:var(--radius-pill);
  background:var(--divider-subtle);
  color:var(--fg-secondary);
  letter-spacing:0.03em;
  font-family:var(--font-sans);
}
```

### 头像（前端 SVG hash）

```css
.avatar-btn{
  background:none; border:2px solid transparent;
  width:36px; height:36px; border-radius:50%;
  overflow:hidden; cursor:pointer;
  transition:border-color .2s, transform .2s;
  display:inline-flex; align-items:center; justify-content:center;
}
.avatar-btn:hover{ border-color:var(--accent); transform:scale(1.05); }
.avatar-shapes > *{
  animation:avatarFloat 12s ease-in-out infinite alternate;
  transform-origin:center;
}
@keyframes avatarFloat{
  0%{ transform:translate(0,0) rotate(0deg) scale(1); }
  100%{ transform:translate(3px,-3px) rotate(45deg) scale(1.1); }
}
```

**JS**：从 `sha256(email).slice(0,16)` 生成 seed → 4 个抽象几何元素 + 渐变 + 高斯模糊 + 圆形裁剪。

### 模态框

```css
.modal-overlay{
  position:fixed; inset:0;
  background:rgba(0,0,0,0.4);
  backdrop-filter:blur(4px);
  z-index:1000;
  display:flex; align-items:center; justify-content:center;
  padding:24px;
}
.modal-card{
  background:var(--bg-elevated);
  border-radius:var(--radius);
  max-width:800px; width:100%;
  max-height:85vh; overflow-y:auto;
  box-shadow:0 20px 60px rgba(0,0,0,0.3);
}
```

### Markdown 渲染

```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
```

```css
.markdown-body{
  font-size:0.933rem; line-height:1.8;
  font-family:var(--font-sans); font-weight:300;
}
.markdown-body h1, .markdown-body h2, .markdown-body h3{
  font-weight:600; font-family:var(--font-sans);
  margin:1em 0 0.5em;
}
.markdown-body code{
  font-family:var(--mono);
  background:var(--bg);
  padding:1px 6px; border-radius:var(--radius-sm);
}
.markdown-body pre{
  background:var(--bg);
  padding:12px 16px; border-radius:var(--radius);
  overflow-x:auto;
}
.markdown-body blockquote{
  border-left:2px solid var(--divider);
  padding-left:12px; color:var(--fg-secondary);
}
```

**XSS 防护**：必须 `DOMPurify.sanitize()`，渲染失败降级纯文本。

---

## 4. 暗色模式

切换逻辑：

```javascript
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const savedTheme = localStorage.getItem('theme');
document.documentElement.dataset.theme =
  savedTheme || (prefersDark ? 'dark' : 'light');

window.matchMedia('(prefers-color-scheme: dark)')
  .addEventListener('change', e => {
    if (!localStorage.getItem('theme')) {
      document.documentElement.dataset.theme = e.matches ? 'dark' : 'light';
    }
  });
```

**避坑**：
- 永远 `var(--xxx)`，哪怕 `background:white` 也要写成 `background:var(--bg-elevated)`
- 半透明背景要单独覆盖（导航栏的 `rgba(255,255,255,0.72)` 在暗色下要换成 `rgba(26,26,28,0.72)`）
- 暗色下阴影要更深（`rgba(0,0,0,0.4)`）

---

## 5. 响应式

```css
/* 默认：桌面端 > 1024 */
@media (max-width:1024px){
  .container{ padding:24px 20px 48px; }
}
@media (max-width:768px){
  .stats-grid{ grid-template-columns:repeat(3, 1fr); }
  .stat-card:nth-child(3){ border-right:none; }
  .stat-card:nth-child(n+4){ border-top:1px solid var(--divider-subtle); }
}
@media (max-width:640px){
  .header-inner{ flex-wrap:wrap; gap:16px; padding:12px 16px; }
  .container{ padding:20px 16px 40px; }
  .stats-grid{ grid-template-columns:repeat(2, 1fr); }
  .fab{ right:16px; bottom:16px; }
}
```

**原则**：触摸目标 ≥ 44px；字号最小 14px；间距减半但不能减到 0；导航 tab 太多 → 横向滚动，**不用汉堡菜单**。

---

## 6. 动效

```css
--ease-apple: cubic-bezier(.2,.7,.2,1);

@keyframes panelSlideIn{
  0%{ opacity:0; transform:translateY(14px); }
  100%{ opacity:1; transform:none; }
}
.panel{ animation:panelSlideIn .42s var(--ease-apple) both; }

@keyframes pulse{
  0%,100%{ opacity:1; box-shadow:0 0 0 0 rgba(52,199,89,0.3); }
  50%{ opacity:.5; box-shadow:0 0 0 5px rgba(52,199,89,0); }
}
.live-dot{ animation:pulse 2.5s ease infinite; }

@keyframes shimmer{
  0%{ background-position:100% 50%; }
  100%{ background-position:0 50%; }
}
.skeleton{
  background:linear-gradient(90deg, var(--bg) 25%, var(--bg-hover) 37%, var(--bg) 63%);
  background-size:400% 100%;
  animation:shimmer 1.6s ease infinite;
}
```

**原则**：所有过渡 ≤ 0.4s；用 `cubic-bezier` 不用 `linear`；少而精（面板切换 / 点击反馈 / 加载完成）；避免弹跳旋转闪烁。

---

## 7. 反例（不要做）

```css
/* ❌ 彩色卡片堆砌 */
.card-grad-1{ background:linear-gradient(135deg, #FF6B6B, #FF8E8E); }

/* ❌ 大圆角 / 拟物化 */
.card{ border-radius:24px; box-shadow:0 10px 40px rgba(0,0,0,0.1); }

/* ❌ 装饰性渐变背景 */
body{ background:linear-gradient(45deg, #FFE4E1, #E0F6FF, #F0FFF4); }

/* ❌ 所有按钮都蓝色 */
button{ background:#0071E3; color:white; }

/* ❌ 硬编码颜色 */
.title{ color:#1D1D1F; }
```

---

## 8. 自检 checklist

每次完成一版前端，问自己：

- [ ] 不用滚动条就能扫到主信息（视觉层级清晰）
- [ ] 模块间间距 ≥ 48px
- [ ] 没有 > 12px 圆角的元素
- [ ] 没有彩色块 / 渐变背景
- [ ] 蓝色只用在关键行动点
- [ ] 暗色模式下无白色漏网
- [ ] 移动端（375px 宽）布局正常
- [ ] loading / 空 / 错误三态都有反馈
- [ ] 字号系统统一（不出现 17px / 19px 突兀值）
- [ ] 所有 SVG icon 颜色用 `currentColor`
- [ ] 触摸目标 ≥ 44px

---

## 9. 给 AI 的设计指令模板

让 AI 实现 UI 时，把这段贴进去作为前提：

```markdown
## 设计风格前提

参考 Apple 官网（apple.com/cn）的极简风格：

1. 背景 `#F5F5F7` 极淡冷灰
2. 正文 `#1D1D1F` 深炭黑
3. 次要 `#6E6E73` 中灰
4. 字体：默认 Noto Serif SC（衬线），辅助文字 PingFang SC（无衬线）
5. 分割线 1px 细横线（#E8E8ED），不用卡片边框
6. 圆角 4-6px，绝不超过 12px
7. 阴影极淡或无
8. 蓝色 `#0071E3` 仅用在关键 CTA / 链接
9. 按钮：默认白底黑字 + 1px 边框；主按钮 = 黑底白字
10. 模块间距 ≥ 48px
11. 响应式：> 1024 桌面，640-1024 平板，< 640 手机
12. 暗色模式必须用 CSS 变量，所有颜色不能硬编码

不允许：渐变背景 / 卡片阴影堆叠 / 大圆角 / 大块彩色 / 刺眼饱和色
```

---

## 10. 字体加载

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@200;300;400;500;600;700;900&display=swap" rel="stylesheet">
```

如果产品不需要衬线（如纯数据后台），去掉 Noto Serif SC，直接用系统字体栈。

---

*本设计系统抽离自 AutoTreehole 2026 年 7-8 月迭代。*