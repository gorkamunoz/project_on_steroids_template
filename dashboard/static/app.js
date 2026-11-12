// Render LaTeX produced by core.render(): <span class="math"> / <div class="math display">
document.querySelectorAll(".math").forEach(el => {
  try {
    katex.render(el.textContent, el, { displayMode: el.classList.contains("display"), throwOnError: false });
  } catch (e) { el.title = e.message; }
});
// Highlight the current section in the nav bar
const sec = "/" + location.pathname.split("/")[1];
document.querySelectorAll("nav a").forEach(a => {
  if (sec !== "/" && a.getAttribute("href").startsWith(sec)) a.classList.add("active");
});
// Ctrl+Enter submits comment forms
document.querySelectorAll("textarea").forEach(t => t.addEventListener("keydown", e => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) t.form.submit();
}));
