import { createInterviewsView } from "./interviewsView.js";
import { createReportsView } from "./reportsView.js";

function wireTabs(onSwitch) {
  const tabs = document.querySelectorAll(".tab");
  const views = {
    interviews: document.getElementById("view-interviews"),
    reports: document.getElementById("view-reports"),
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.getAttribute("data-view");
      tabs.forEach((t) => t.classList.toggle("is-active", t === tab));
      Object.entries(views).forEach(([key, el]) => {
        if (!el) return;
        const active = key === name;
        el.hidden = !active;
        el.classList.toggle("is-active", active);
      });
      onSwitch?.(name);
    });
  });
}

async function bootstrap() {
  const interviews = createInterviewsView();
  const reports = createReportsView();

  wireTabs((name) => {
    if (name === "reports") {
      reports.refresh().catch(console.error);
    } else if (name === "interviews") {
      interviews.refresh().catch(console.error);
    }
  });

  try {
    await interviews.init();
  } catch (err) {
    console.error(err);
    alert(`Failed to load interview module: ${err.message}`);
  }

  try {
    await reports.init();
  } catch (err) {
    console.error(err);
  }
}

bootstrap();
