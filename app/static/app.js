(() => {
  const dtFmt = new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  function relativeLabel(date, now) {
    const seconds = Math.round((now.getTime() - date.getTime()) / 1000);
    if (seconds < 45) return "just now";
    const minutes = Math.max(1, Math.floor(seconds / 60));
    if (minutes < 60) {
      return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
    }
    const hours = Math.floor(seconds / 3600);
    if (hours < 24) {
      return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
    }
    const days = Math.floor(seconds / 86400);
    if (days === 1) return "yesterday";
    if (days < 7) return `${days} days ago`;
    return dtFmt.format(date);
  }

  const now = new Date();
  document.querySelectorAll("time[data-utc]").forEach((el) => {
    const date = new Date(el.dateTime);
    if (Number.isNaN(date.getTime())) return;
    const local = dtFmt.format(date);
    el.textContent = local;
    el.removeAttribute("title");
    el.title = `${local} (${el.dateTime})`;
    const rel = el.closest(".when")?.querySelector("[data-relative]");
    if (rel) rel.textContent = relativeLabel(date, now);
  });

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    const original = btn.textContent;
    btn.addEventListener("click", async () => {
      const value = btn.getAttribute("data-copy") || "";
      try {
        await navigator.clipboard.writeText(value);
        btn.textContent = "Copied";
      } catch {
        btn.textContent = "Copy failed";
      }
      window.setTimeout(() => {
        btn.textContent = original;
      }, 1600);
    });
  });
})();
