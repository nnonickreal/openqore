// =======================================================================
// State & Navigation
// =======================================================================
const state = {
  firmwarePath: null,
  packed: null,
  moduleRef: null,
  sessionId: null,
  staticFields: [],
  dynamicFields: [],
  currentTab: 'openqore',
};

const besotaState = {
  firmwarePath: null,
  connected: false,
  isFlashing: false,
};

const view = document.getElementById('view');
const api = () => window.pywebview.api;
const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function clearView() { view.innerHTML = ''; }

function section(titleText) {
  const s = el('section');
  s.appendChild(el('h2', null, titleText.toLowerCase()));
  view.appendChild(s);
  return s;
}

function actionsRow(container, buttons) {
  const row = el('div', 'row');
  buttons.forEach(([text, cls, handler]) => {
    // Buttons start with a capital letter
    const b = el('button', cls || '', text);
    b.addEventListener('click', handler);
    row.appendChild(b);
  });
  container.appendChild(row);
}

// ---------- Top Tab Switcher Animation ----------
function switchTab(tabName) {
  if (state.currentTab === tabName) return;
  state.currentTab = tabName;

  const tabOpenqore = $('tabOpenqore');
  const tabBesota = $('tabBesota');
  const viewOpenqore = $('viewOpenqore');
  const viewBesota = $('viewBesota');
  const footerNote = $('footerNote');

  if (tabName === 'openqore') {
    tabOpenqore.classList.add('active');
    tabBesota.classList.remove('active');
    viewBesota.classList.remove('active');
    viewOpenqore.classList.add('active');
    footerNote.textContent = 'openqore';
  } else {
    tabBesota.classList.add('active');
    tabOpenqore.classList.remove('active');
    viewOpenqore.classList.remove('active');
    viewBesota.classList.add('active');
    footerNote.textContent = 'besota was written using LLM models for coding and was tested on actual hardware.';
  }
}

$('tabOpenqore').addEventListener('click', () => switchTab('openqore'));
$('tabBesota').addEventListener('click', () => switchTab('besota'));

// ---------- Global External Link Interceptor ----------
document.addEventListener('click', (e) => {
  const link = e.target.closest('a');
  if (link && link.href && (link.href.startsWith('http://') || link.href.startsWith('https://'))) {
    e.preventDefault();
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_browser) {
      window.pywebview.api.open_browser(link.href);
    } else {
      window.open(link.href, '_blank');
    }
  }
});

// =======================================================================
// Shared Modal Helper
// =======================================================================
function openModal(titleText) {
  const backdrop = el('div', 'modal-backdrop');
  backdrop.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.82);display:flex;align-items:center;justify-content:center;z-index:9999;backdrop-filter:blur(4px);padding:16px;';

  const box = el('div', 'modal-box');
  box.style.cssText = 'background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-lg);width:620px;max-width:100%;max-height:88vh;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:18px;color:var(--fg);box-shadow:0 16px 48px rgba(0,0,0,0.9);animation:tabFadeSlide 0.22s ease forwards;';

  const header = el('div');
  header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:14px;';

  const title = el('h2', null, titleText.toLowerCase());
  title.style.cssText = 'margin:0;font-family:"ndot47","Geist",monospace;font-size:13px;letter-spacing:0.08em;color:var(--fg-dim);text-transform:lowercase;';
  header.appendChild(title);

  const closeBtn = el('button', 'btn-close', '✕');
  closeBtn.style.cssText = 'background:transparent;border:none;color:var(--fg-dim);font-size:16px;cursor:pointer;padding:4px 8px;border-radius:var(--radius-sm);line-height:1;box-shadow:none;';
  closeBtn.addEventListener('click', () => backdrop.remove());
  header.appendChild(closeBtn);

  const content = el('div');
  content.style.cssText = 'display:flex;flex-direction:column;gap:18px;';

  box.appendChild(header);
  box.appendChild(content);
  backdrop.appendChild(box);
  document.body.appendChild(backdrop);

  return { content, close: () => backdrop.remove() };
}

function radioGroup(name, options, currentValue, onChange) {
  const group = el('div', 'radio-group');
  options.forEach(([val, text]) => {
    const opt = el('label', 'radio-opt' + (currentValue === val ? ' selected' : ''));
    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = name;
    radio.checked = currentValue === val;
    radio.addEventListener('change', () => {
      [...group.children].forEach(c => c.classList.remove('selected'));
      opt.classList.add('selected');
      onChange(val);
    });
    opt.appendChild(radio);

    const labelTitle = el('div', 'radio-opt-title', text.toLowerCase());
    labelTitle.style.cssText = 'word-break:break-word;overflow-wrap:anywhere;';
    opt.appendChild(labelTitle);
    group.appendChild(opt);
  });
  return group;
}

function moduleRadioGroup(modules, currentValue, onChange, onShowInfo) {
  const group = el('div', 'radio-group');
  modules.forEach(m => {
    const opt = el('label', 'radio-opt' + (currentValue === m.ref ? ' selected' : ''));
    opt.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:14px;';

    const left = el('div');
    left.style.cssText = 'display:flex;align-items:center;gap:12px;flex:1;min-width:0;';

    const radio = document.createElement('input');
    radio.type = 'radio';
    radio.name = 'module';
    radio.checked = currentValue === m.ref;
    radio.addEventListener('change', () => {
      [...group.children].forEach(c => c.classList.remove('selected'));
      opt.classList.add('selected');
      onChange(m.ref);
    });

    const title = el('div', 'radio-opt-title', `${m.name}  [${m.kind}/${m.chip}]`);
    title.style.cssText = 'word-break:break-word;overflow-wrap:anywhere;line-height:1.35;';

    left.appendChild(radio);
    left.appendChild(title);

    // Button capitalized
    const infoBtn = el('button', 'btn-sm', 'Details');
    infoBtn.type = 'button';
    infoBtn.style.cssText = 'padding:6px 14px;font-size:11px;letter-spacing:0.04em;flex-shrink:0;';
    infoBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      onShowInfo(m);
    });

    opt.appendChild(left);
    opt.appendChild(infoBtn);
    group.appendChild(opt);
  });
  return group;
}

function showModuleDetails(mod) {
  const modal = openModal(mod.name.toLowerCase());
  const meta = el('div', 'notice');
  meta.textContent = `type: ${mod.kind.toLowerCase()} · chip: ${mod.chip || 'generic'}`;
  modal.content.appendChild(meta);

  const descLabel = el('label', null, 'module description:');
  modal.content.appendChild(descLabel);

  const descBox = el('div');
  descBox.style.cssText = 'white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;background:#000;padding:16px;border:1px solid var(--line);border-radius:var(--radius-md);font-size:12.5px;line-height:1.55;max-height:48vh;overflow-y:auto;color:var(--fg);font-family:inherit;';
  descBox.textContent = mod.description || 'no description provided for this module.';
  modal.content.appendChild(descBox);
}

function renderField(field, container, valuesStore) {
  const wrap = el('div', 'field');
  wrap.appendChild(el('label', null, field.label.toLowerCase()));
  if (field.help) wrap.appendChild(el('div', 'notice', field.help.toLowerCase()));

  if (field.kind === 'bool') {
    valuesStore[field.id] = field.default;
    wrap.appendChild(radioGroup(field.id, [[true, 'yes'], [false, 'no']], field.default,
      (v) => { valuesStore[field.id] = v; }));
  } else if (field.kind === 'choice') {
    valuesStore[field.id] = field.default;
    wrap.appendChild(radioGroup(field.id, field.choices || [], field.default,
      (v) => { valuesStore[field.id] = v; }));
  } else if (field.kind === 'int' || field.kind === 'float') {
    const input = document.createElement('input');
    input.type = 'number';
    if (field.min !== null && field.min !== undefined) input.min = field.min;
    if (field.max !== null && field.max !== undefined) input.max = field.max;
    if (field.kind === 'float') input.step = 'any';
    input.value = field.default ?? '';
    valuesStore[field.id] = field.default;
    input.addEventListener('input', () => {
      let v = field.kind === 'int' ? parseInt(input.value, 10) : parseFloat(input.value);
      if (Number.isNaN(v)) return;
      if (field.min !== null && field.min !== undefined && v < field.min) v = field.min;
      if (field.max !== null && field.max !== undefined && v > field.max) v = field.max;
      valuesStore[field.id] = v;
    });
    wrap.appendChild(input);
  } else if (field.kind !== 'info') {
    const input = document.createElement('input');
    input.type = 'text';
    input.value = field.default ?? '';
    valuesStore[field.id] = field.default ?? '';
    input.addEventListener('input', () => { valuesStore[field.id] = input.value; });
    wrap.appendChild(input);
  }

  container.appendChild(wrap);
}

async function openArchiveModal(afterPick) {
  const modal = openModal('online firmware archive');
  const defaultUrl = await api().get_default_catalog_url();

  const urlWrap = el('div', 'field');
  urlWrap.appendChild(el('label', null, 'catalog json url / local file:'));
  const urlInput = document.createElement('input');
  urlInput.type = 'text';
  urlInput.value = defaultUrl;
  urlWrap.appendChild(urlInput);
  modal.content.appendChild(urlWrap);

  const fetchBtn = el('button', '', 'Fetch catalog');
  modal.content.appendChild(fetchBtn);

  const catalogArea = el('div');
  catalogArea.style.cssText = 'display:flex;flex-direction:column;gap:18px;';
  modal.content.appendChild(catalogArea);

  async function loadCatalog() {
    catalogArea.innerHTML = '';
    const status = el('div', 'notice', 'fetching catalog index...');
    catalogArea.appendChild(status);

    const res = await api().fetch_firmware_catalog(urlInput.value.trim());
    catalogArea.innerHTML = '';

    if (!res.ok) {
      catalogArea.appendChild(el('div', 'notice', `failed to fetch catalog: ${res.error}`));
      return;
    }

    const vendors = res.vendors || [];
    if (!vendors.length) {
      catalogArea.appendChild(el('div', 'notice', 'catalog contains no vendor definitions.'));
      return;
    }

    const vendorWrap = el('div', 'field');
    vendorWrap.appendChild(el('label', null, '1. select vendor:'));
    const vendorSelect = document.createElement('select');
    vendors.forEach((v, idx) => {
      const opt = document.createElement('option');
      opt.value = idx;
      opt.textContent = `${v.name || 'generic'} (${(v.devices || []).length} devices)`;
      vendorSelect.appendChild(opt);
    });
    vendorWrap.appendChild(vendorSelect);
    catalogArea.appendChild(vendorWrap);

    const devWrap = el('div', 'field');
    devWrap.appendChild(el('label', null, '2. select headphone model:'));
    const devSelect = document.createElement('select');
    devWrap.appendChild(devSelect);
    catalogArea.appendChild(devWrap);

    const verWrap = el('div', 'field');
    verWrap.appendChild(el('label', null, '3. select firmware version:'));
    const verSelect = document.createElement('select');
    verWrap.appendChild(verSelect);
    catalogArea.appendChild(verWrap);

    const fwNote = el('div', 'notice');
    fwNote.style.cssText = 'word-break:break-word;overflow-wrap:anywhere;line-height:1.45;';
    catalogArea.appendChild(fwNote);

    function updateDevices() {
      devSelect.innerHTML = '';
      const vendor = vendors[parseInt(vendorSelect.value, 10)];
      const devices = (vendor && vendor.devices) ? vendor.devices : [];

      devices.forEach((d, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        const tag = d.model_code || d.chip;
        opt.textContent = tag ? `${d.name || 'unnamed'} (${tag})` : (d.name || 'unnamed');
        devSelect.appendChild(opt);
      });
      updateFirmwares();
    }

    function updateFirmwares() {
      verSelect.innerHTML = '';
      const vendor = vendors[parseInt(vendorSelect.value, 10)];
      const devices = (vendor && vendor.devices) ? vendor.devices : [];
      const dev = devices[parseInt(devSelect.value, 10)];
      const fws = (dev && dev.firmwares) ? dev.firmwares : [];

      fws.forEach((f, idx) => {
        const opt = document.createElement('option');
        opt.value = idx;
        opt.textContent = `v${f.version || 'unknown'} ${f.notes ? ('— ' + f.notes.replace(/\n/g, ' ')) : ''}`;
        verSelect.appendChild(opt);
      });
      updateFwNote();
    }

    function updateFwNote() {
      const vendor = vendors[parseInt(vendorSelect.value, 10)];
      const devices = (vendor && vendor.devices) ? vendor.devices : [];
      const dev = devices[parseInt(devSelect.value, 10)];
      const fw = (dev && dev.firmwares) ? dev.firmwares[parseInt(verSelect.value, 10)] : null;

      if (fw) {
        let noteText = `version: v${fw.version || 'unknown'}\n`;
        if (fw.sha256) noteText += `sha256: ${fw.sha256}\n`;
        if (fw.notes) noteText += `\nchangelog:\n${fw.notes}`;
        fwNote.textContent = noteText;
        fwNote.style.display = 'block';
      } else {
        fwNote.style.display = 'none';
      }
    }

    vendorSelect.addEventListener('change', updateDevices);
    devSelect.addEventListener('change', updateFirmwares);
    verSelect.addEventListener('change', updateFwNote);
    updateDevices();

    const progressWrap = el('div', 'progress-wrap');
    progressWrap.style.display = 'none';
    const bar = el('div', 'progress-bar');
    progressWrap.appendChild(bar);
    catalogArea.appendChild(progressWrap);

    const statusText = el('div', 'notice');
    statusText.style.display = 'none';
    statusText.style.cssText += 'word-break:break-word;overflow-wrap:anywhere;';
    catalogArea.appendChild(statusText);

    // Button capitalized
    const dlBtn = el('button', 'danger', 'Download & verify firmware');
    catalogArea.appendChild(dlBtn);

    async function triggerDownload() {
      const vendor = vendors[parseInt(vendorSelect.value, 10)];
      const dev = (vendor && vendor.devices) ? vendor.devices[parseInt(devSelect.value, 10)] : null;
      const fw = (dev && dev.firmwares) ? dev.firmwares[parseInt(verSelect.value, 10)] : null;
      if (!fw || !fw.url) return;

      const cleanDevName = (dev.name || 'firmware').replace(/[^a-zA-Z0-9]/g, '_');
      const filename = `${cleanDevName}_${fw.version || 'dl'}.bin`;

      progressWrap.style.display = 'block';
      statusText.style.display = 'block';
      statusText.textContent = `downloading ${filename}...`;
      dlBtn.disabled = true;

      const poll = setInterval(async () => {
        const events = await api().poll_events();
        events.forEach(e => {
          if (e.type === 'progress') {
            const pct = Math.max(0, Math.min(100, e.percent));
            bar.style.width = pct.toFixed(1) + '%';
            statusText.textContent = `downloading: ${pct.toFixed(1)}% (${e.done}/${e.total})`;
          }
        });
      }, 150);

      const res = await api().download_catalog_firmware(fw.url, filename, fw.crc32 || null);
      clearInterval(poll);
      dlBtn.disabled = false;

      if (!res.ok) {
        statusText.textContent = `download error: ${res.error}`;
        return;
      }

      if (!res.crc_valid) {
        bar.style.width = '0%';
        statusText.textContent = `crc check failed: ${res.crc_message}`;
        const retry = confirm(`${res.crc_message}\n\ndo you want to re-download the file?`);
        if (retry) return triggerDownload();
      }

      statusText.textContent = `verified: ${res.crc_message}`;
      modal.close();
      await afterPick(res.path);
    }

    dlBtn.addEventListener('click', triggerDownload);
  }

  fetchBtn.addEventListener('click', loadCatalog);
  loadCatalog();
}

async function screenFile() {
  clearView();
  const s = section('1. firmware file');
  const drop = el('div', 'filedrop', 'click to select a local firmware .bin file');

  const divider = el('div', 'or-divider');
  divider.appendChild(el('span', null, 'or download from catalog'));

  const archiveBtn = el('button', '', 'Browse firmware archive');
  archiveBtn.style.cssText = 'width:100%;';

  const meta = el('div', 'filemeta');
  const controls = el('div', 'file-controls');

  s.appendChild(drop);
  s.appendChild(divider);
  s.appendChild(archiveBtn);
  s.appendChild(meta);
  s.appendChild(controls);

  async function afterPick(picked) {
    const path = (typeof picked === 'object' && picked !== null) ? picked.path : picked;
    state.firmwarePath = path;
    const info = await api().detect_packed(path);
    state.packed = info.packed;

    meta.innerHTML = '';
    const selDiv = el('div', null);
    selDiv.style.cssText = 'word-break:break-word;overflow-wrap:anywhere;line-height:1.45;';
    selDiv.appendChild(el('b', null, 'selected: '));
    selDiv.appendChild(document.createTextNode(path));
    meta.appendChild(selDiv);

    const detectDiv = el('div', null,
      `auto-detected: firmware looks ${info.packed ? 'packed' : 'unpacked'} (override below if needed)`);
    detectDiv.style.cssText = 'margin-top:4px;word-break:break-word;overflow-wrap:anywhere;';
    meta.appendChild(detectDiv);

    controls.innerHTML = '';
    renderPackedChoice(controls);
  }

  drop.addEventListener('click', async () => {
    const res = await api().pick_file();
    if (res) await afterPick(res);
  });

  archiveBtn.addEventListener('click', () => openArchiveModal(afterPick));
  if (state.firmwarePath) await afterPick(state.firmwarePath);
}

function renderPackedChoice(container) {
  const group = radioGroup('packed',
    [[true, 'firmware is packed (ota/lzma container)'], [false, 'firmware is a raw/unpacked image']],
    state.packed, (v) => { state.packed = v; });
  container.appendChild(group);
  actionsRow(container, [['Continue', '', screenModule]]);
}

async function screenModule() {
  clearView();
  const s = section('2. select a patch module');
  const modules = await api().list_modules();
  if (!modules.length) {
    s.appendChild(el('div', 'notice', 'no modules found in modules_json/ or modules_py/.'));
  }

  const group = moduleRadioGroup(
    modules,
    state.moduleRef,
    (v) => { state.moduleRef = v; },
    (mod) => { showModuleDetails(mod); }
  );
  s.appendChild(group);

  actionsRow(s, [
    ['Back', '', screenFile],
    ['Continue', '', async () => {
      if (!state.moduleRef) return;
      const res = await api().start_session(state.moduleRef, state.firmwarePath, state.packed);
      state.sessionId = res.session_id;
      state.staticFields = res.fields;
      screenStatic();
    }],
  ]);
}

async function screenStatic() {
  clearView();
  const s = section('3. module options');
  const values = {};
  state.staticFields.forEach(f => renderField(f, s, values));
  actionsRow(s, [
    ['Back', '', screenModule],
    ['Continue', '', async () => {
      const res = await api().submit_static(state.sessionId, values);
      state.dynamicFields = res.fields;
      if (state.dynamicFields.length) screenDynamic();
      else screenRun({});
    }],
  ]);
}

async function screenDynamic() {
  clearView();
  const s = section('4. detected items');
  const values = {};
  state.dynamicFields.forEach(f => renderField(f, s, values));
  actionsRow(s, [
    ['Back', '', screenStatic],
    ['Run patch', 'danger', () => screenRun(values)],
  ]);
}

async function screenRun(dynamicValues) {
  clearView();
  const s = section('5. patching');

  const statusRow = el('div', 'status-row');
  const dot = el('span', 'dot on');
  const statusText = el('span', null, 'select output location...');
  statusText.style.cssText = 'word-break:break-word;overflow-wrap:anywhere;';
  statusRow.appendChild(dot);
  statusRow.appendChild(statusText);
  s.appendChild(statusRow);

  const log = el('div', 'log');
  s.appendChild(log);

  const defaultName = (state.firmwarePath.split(/[\\/]/).pop() || 'firmware').replace(/\.bin$/i, '') + '_patched.bin';
  const outputPath = await api().pick_save_path(defaultName);
  if (!outputPath) { screenDynamic(); return; }

  statusText.textContent = 'working...';
  await api().run_patch(state.sessionId, dynamicValues, outputPath);

  const poll = setInterval(async () => {
    const events = await api().poll_events();
    events.forEach(e => {
      if (e.type === 'log') {
        const line = el('div', 'l-info', e.message);
        log.appendChild(line);
        log.scrollTop = log.scrollHeight;
      } else if (e.type === 'done') {
        clearInterval(poll);
        dot.className = e.ok ? 'dot on' : 'dot err';
        statusText.textContent = e.ok ? ('done: ' + e.output) : ('failed: ' + e.error);

        const actions = [['Start over', '', () => {
          Object.assign(state, { firmwarePath: null, packed: null, moduleRef: null, sessionId: null });
          screenFile();
        }]];

        if (e.ok) {
          actions.push(['⚡ Flash via besota', '', () => {
            onFirmwareSelected({
              path: e.output,
              name: e.output.split(/[\\/]/).pop(),
              size: 0
            });
            switchTab('besota');
          }]);
        }

        actionsRow(s, actions);
      }
    });
  }, 200);
}

// =======================================================================
// besota Front-end Implementation
// =======================================================================
function uiLog(msg, cls) {
  cls = cls || "l-info";
  const line = document.createElement("div");
  line.className = cls;
  const ts = new Date().toLocaleTimeString();
  line.textContent = "[" + ts + "] " + msg;
  const log = $("besotaLog");
  if (log) {
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }
}

function setStatus(text, kind) {
  $("connStatus").textContent = text;
  $("connDot").className = "dot" + (kind === "on" ? " on" : kind === "err" ? " err" : "");
}

function setProgress(offset, total, speed, eta) {
  const pct = total ? (offset / total) * 100 : 0;
  $("besotaProgressBar").style.width = pct.toFixed(1) + "%";
  $("progressPct").textContent = pct.toFixed(1) + "%";
  $("progressBytes").textContent = Math.floor(offset / 1024) + " / " + Math.floor(total / 1024) + " KB";
  $("progressSpeed").textContent = speed.toFixed(1) + " KB/s";
  $("progressEta").textContent = "eta " + Math.max(0, Math.round(eta)) + "s";
}

function updateFlashButton() {
  $("btnFlash").disabled = !(besotaState.firmwarePath && besotaState.connected && !besotaState.isFlashing);
}

document.querySelectorAll("#protocolGroup .radio-opt").forEach(opt => {
  opt.addEventListener("click", () => {
    document.querySelectorAll("#protocolGroup .radio-opt").forEach(o => o.classList.remove("selected"));
    opt.classList.add("selected");
    opt.querySelector("input").checked = true;

    const preset = $("otaPreset");
    if (opt.dataset.proto === "v1") preset.value = "0x18000";
    if (opt.dataset.proto === "v2") preset.value = "0x20000";
    onOtaPresetChange();
  });
});

function getSelectedProtocol() {
  const checked = document.querySelector('input[name="proto"]:checked');
  return checked ? checked.value : "v1";
}

function onOtaPresetChange() {
  const preset = $("otaPreset").value;
  const custom = $("otaCustom");
  if (preset === "custom") {
    custom.disabled = false;
    custom.focus();
  } else {
    custom.disabled = true;
    custom.value = preset;
  }
}
$("otaPreset").addEventListener("change", onOtaPresetChange);

function getOtaAddress() {
  const preset = $("otaPreset").value;
  return preset === "custom" ? $("otaCustom").value.trim() : preset;
}

function onFirmwareSelected(fileInfo) {
  if (!fileInfo) return;
  besotaState.firmwarePath = fileInfo.path;
  $("besotaFileMeta").innerHTML = "<b>" + fileInfo.name + "</b>" + (fileInfo.size ? " &middot; " + fileInfo.size.toLocaleString() + " B" : "");
  uiLog("selected firmware: " + fileInfo.path, "l-ok");
  updateFlashButton();
}

const besotaDropZone = $("besotaDropZone");
besotaDropZone.addEventListener("click", async () => {
  const result = await api().pick_file();
  onFirmwareSelected(result);
});

const btnBesotaArchive = $('btnBesotaArchive');
if (btnBesotaArchive) {
  btnBesotaArchive.addEventListener('click', () => {
    openArchiveModal(async (picked) => {
      const path = (typeof picked === 'object' && picked !== null) ? picked.path : picked;
      if (!path) return;
      if (api().set_firmware_by_path) {
        await api().set_firmware_by_path(path);
      }
      onFirmwareSelected({
        path: path,
        name: path.split(/[\\/]/).pop(),
        size: 0
      });
    });
  });
}

$("btnScan").addEventListener("click", async () => {
  const name = $("scanName").value.trim();
  if (!name) { uiLog("enter a device name filter first.", "l-err"); return; }
  const seconds = parseInt($("scanSeconds").value, 10) || 8;

  $("btnScan").disabled = true;
  $("btnScan").textContent = "Scanning...";
  uiLog(`scanning for "${name}" (${seconds}s)...`);
  await api().scan_devices(name, seconds);
});

function onScanResults(results) {
  $("btnScan").disabled = false;
  $("btnScan").textContent = "Scan";
  const select = $("scanResults");
  select.innerHTML = "";

  if (!results.length) {
    select.innerHTML = '<option value="">-- no devices found --</option>';
    uiLog("no matching devices found.", "l-err");
    return;
  }

  results.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d.address;
    opt.textContent = `${d.name}  [${d.address}]`;
    select.appendChild(opt);
  });
  $("address").value = results[0].address;
  uiLog(`found ${results.length} matching device(s).`, "l-ok");
}

function onScanFailed(err) {
  $("btnScan").disabled = false;
  $("btnScan").textContent = "Scan";
  uiLog("scan failed: " + err, "l-err");
}

$("scanResults").addEventListener("change", (e) => {
  if (e.target.value) $("address").value = e.target.value;
});

$("btnConnect").addEventListener("click", async () => {
  const addr = $("address").value.trim().toUpperCase();
  const macRe = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/;
  if (!macRe.test(addr)) {
    uiLog("invalid mac address format.", "l-err");
    return;
  }

  $("btnConnect").disabled = true;
  $("btnConnect").textContent = "Connecting...";
  setStatus("looking up besota service...", null);
  uiLog("connecting to " + addr + "...");
  await api().connect(addr);
});

function onConnected(address) {
  besotaState.connected = true;
  $("btnConnect").disabled = true;
  $("btnConnect").textContent = "Connect";
  $("btnDisconnect").disabled = false;
  setStatus("connected to " + address, "on");
  uiLog("connected.", "l-ok");
  updateFlashButton();
}

function onConnectFailed(err) {
  $("btnConnect").disabled = false;
  $("btnConnect").textContent = "Connect";
  setStatus("connection failed: " + err, "err");
  uiLog("connection failed: " + err, "l-err");
}

$("btnDisconnect").addEventListener("click", async () => {
  await api().disconnect();
  besotaState.connected = false;
  $("btnConnect").disabled = false;
  $("btnDisconnect").disabled = true;
  setStatus("not connected.", null);
  uiLog("disconnected.");
  updateFlashButton();
});

$("btnFlash").addEventListener("click", async () => {
  if (!besotaState.firmwarePath) { uiLog("select a firmware file first.", "l-err"); return; }
  if (!besotaState.connected) { uiLog("connect to a device first.", "l-err"); return; }

  besotaState.isFlashing = true;
  $("btnFlash").disabled = true;
  $("btnAbort").disabled = false;
  $("besotaProgressBar").style.width = "0%";
  uiLog("============================================================", "l-tx");
  uiLog("starting flash...", "l-tx");

  await api().start_flash(getSelectedProtocol(), getOtaAddress());
});

$("btnAbort").addEventListener("click", async () => {
  $("btnAbort").disabled = true;
  uiLog("abort requested...", "l-err");
  await api().abort();
});

function onFlashDone(err) {
  besotaState.isFlashing = false;
  $("btnAbort").disabled = true;

  besotaState.connected = false;
  $("btnConnect").disabled = false;
  $("btnDisconnect").disabled = true;
  setStatus("not connected.", null);
  updateFlashButton();

  if (!err) {
    uiLog("done! firmware update applied, device is rebooting.", "l-ok");
  } else {
    uiLog("fatal: " + err, "l-err");
  }
}

// =======================================================================
// Bootstrapping
// =======================================================================
function initApp() {
  screenFile();
  uiLog("besota flasher initialized.", "l-info");
}

if (window.pywebview) {
  initApp();
} else {
  window.addEventListener('pywebviewready', initApp);
}