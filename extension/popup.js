// BiliDL 浏览器扩展 popup 逻辑：获取当前标签页 URL 并推送到本地 /api/push
const $ = (id) => document.getElementById(id);
const status = (msg, cls) => {
  const e = $("status");
  e.textContent = msg;
  e.className = "status " + (cls || "");
};

async function postJson(url, data) {
  // 用 text/plain 避免触发 CORS 预检；服务端按 JSON 解析 body
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

$("capture").addEventListener("click", async () => {
  const base = ($("base").value || "").trim().replace(/\/+$/, "");
  if (!base) { status("请填写 BiliDL 地址", "err"); return; }
  $("capture").disabled = true;
  status("正在获取当前标签页…");
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tab && tab.url;
    if (!url || !/bilibili\.com/.test(url)) {
      status("当前页面不是哔哩哔哩链接：\n" + (url || "(空)"), "err");
      return;
    }
    status("正在推送给 BiliDL：\n" + url);
    const res = await postJson(base + "/api/push", { url });
    if (res && res.error) {
      status("失败：" + res.error, "err");
    } else if (res && res.tasks) {
      const n = (res.tasks || []).length;
      status("已加入下载队列，任务数：" + n +
             "\n请在 BiliDL 窗口查看进度。", "ok");
    } else {
      status("未知返回：" + JSON.stringify(res), "err");
    }
  } catch (e) {
    status("推送失败：" + e.message +
           "\n请确认 BiliDL 已启动且地址正确。", "err");
  } finally {
    $("capture").disabled = false;
  }
});
