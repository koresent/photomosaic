document.addEventListener("DOMContentLoaded", () => {
  let viewer = null;
  let currentMetadata = null;
  let isGenerating = false;
  let pollInterval = null;

  // DOM Elements
  const targetDropzone = document.getElementById("target-dropzone");
  const targetFileInput = document.getElementById("target-file-input");
  const targetThumb = document.getElementById("target-thumb");
  const targetFilename = document.getElementById("target-filename");
  const targetMeta = document.getElementById("target-meta");
  const photosCountText = document.getElementById("photos-count-text");

  const inputCols = document.getElementById("input-cols");
  const badgeCols = document.getElementById("badge-cols");
  const inputTileSize = document.getElementById("input-tile-size");
  const badgeTileSize = document.getElementById("badge-tile-size");
  const inputBlend = document.getElementById("input-blend");
  const badgeBlend = document.getElementById("badge-blend");
  const checkTransparent = document.getElementById("check-transparent");
  const checkUnique = document.getElementById("check-unique");
  const inputTopK = document.getElementById("input-top-k");
  const badgeTopK = document.getElementById("badge-top-k");

  const btnGenerate = document.getElementById("btn-generate");
  const btnGenerateText = document.getElementById("btn-generate-text");
  const progressWrap = document.getElementById("progress-wrap");
  const progressStep = document.getElementById("progress-step");
  const progressPercent = document.getElementById("progress-percent");
  const progressFill = document.getElementById("progress-fill");

  const btnOpenFolder = document.getElementById("btn-open-folder");
  const statsSummary = document.getElementById("stats-summary");
  const previewPlaceholder = document.getElementById("preview-placeholder");
  const btnPlaceholderGen = document.getElementById("btn-placeholder-gen");

  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnHome = document.getElementById("btn-home");

  const studioInspector = document.getElementById("studio-inspector");
  const studioInspectorClose = document.getElementById("studio-inspector-close");
  const studioInspectorImg = document.getElementById("studio-inspector-img");
  const studioInspectorFilename = document.getElementById("studio-inspector-filename");
  const studioInspectorPos = document.getElementById("studio-inspector-pos");

  // Slider bindings
  inputCols.addEventListener("input", (e) => {
    badgeCols.textContent = e.target.value;
  });
  inputTileSize.addEventListener("input", (e) => {
    badgeTileSize.textContent = `${e.target.value} px`;
  });
  inputBlend.addEventListener("input", (e) => {
    badgeBlend.textContent = `${e.target.value}%`;
  });
  inputTopK.addEventListener("input", (e) => {
    badgeTopK.textContent = e.target.value;
  });

  // Target image selection & upload
  targetDropzone.addEventListener("click", () => {
    targetFileInput.click();
  });

  targetFileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (file) {
      await uploadTargetFile(file);
    }
  });

  // Drag and drop for target image
  targetDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    targetDropzone.style.borderColor = "var(--accent-color)";
  });

  targetDropzone.addEventListener("dragleave", () => {
    targetDropzone.style.borderColor = "var(--surface-border)";
  });

  targetDropzone.addEventListener("drop", async (e) => {
    e.preventDefault();
    targetDropzone.style.borderColor = "var(--surface-border)";
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await uploadTargetFile(e.dataTransfer.files[0]);
    }
  });

  async function uploadTargetFile(file) {
    targetFilename.textContent = "Загрузка...";
    const formData = new FormData();
    formData.append("target", file);

    try {
      const res = await fetch("/api/upload-target", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (data.ok) {
        targetFilename.textContent = data.filename;
        targetMeta.textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB • ${file.type}`;
        targetThumb.src = `/source/${data.filename}?t=${Date.now()}`;
      }
    } catch (err) {
      console.error("Upload error:", err);
      targetFilename.textContent = "Ошибка загрузки";
    }
  }

  // OpenSeadragon Init
  function initViewer() {
    viewer = OpenSeadragon({
      id: "openseadragon-studio",
      prefixUrl: "",
      showNavigationControl: false,
      showNavigator: false,
      animationTime: 0.7,
      blendTime: 0.15,
      springStiffness: 9.0,
      maxZoomPixelRatio: 3.5,
      minZoomImageRatio: 0.8,
      visibilityRatio: 0.85,
      constrainDuringPan: true,
      gestureSettingsMouse: {
        clickToZoom: false,
        dblClickToZoom: true
      },
      gestureSettingsTouch: {
        pinchToZoom: true,
        flickEnabled: true
      }
    });

    // Tile click inspector
    viewer.addHandler("canvas-click", (event) => {
      if (!event.quick || !currentMetadata || !currentMetadata.grid) return;

      const viewportPoint = viewer.viewport.pointFromPixel(event.position);
      const imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint);

      const tileSize = currentMetadata.grid.tile_size;
      const cols = currentMetadata.grid.columns;
      const rows = currentMetadata.grid.rows;

      const col = Math.floor(imagePoint.x / tileSize);
      const row = Math.floor(imagePoint.y / tileSize);

      if (col >= 0 && col < cols && row >= 0 && row < rows) {
        const cellIndex = row * cols + col;
        const cell = currentMetadata.cells && currentMetadata.cells[cellIndex];

        if (cell && !cell.empty && cell.photo) {
          studioInspectorFilename.textContent = cell.photo;
          studioInspectorPos.textContent = `Ряд ${row + 1} из ${rows}, Колонка ${col + 1} из ${cols}`;
          studioInspectorImg.src = `/output/assets/thumbs/${cell.thumb}?t=${Date.now()}`;
          studioInspector.style.display = "block";
          return;
        }
      }
      closeInspector();
    });

    btnZoomIn.addEventListener("click", () => viewer.viewport.zoomBy(1.5));
    btnZoomOut.addEventListener("click", () => viewer.viewport.zoomBy(1 / 1.5));
    btnHome.addEventListener("click", () => {
      viewer.viewport.goHome();
      closeInspector();
    });
  }

  function closeInspector() {
    if (studioInspector) studioInspector.style.display = "none";
  }

  if (studioInspectorClose) {
    studioInspectorClose.addEventListener("click", closeInspector);
  }

  // Load existing mosaic into preview
  async function loadExistingMosaic(timestamp) {
    try {
      const res = await fetch(`/output/metadata/mosaic_info.json?t=${timestamp || Date.now()}`);
      if (res.ok) {
        currentMetadata = await res.json();
        const totalFilled = currentMetadata.stats.filled_cells !== undefined ? currentMetadata.stats.filled_cells : currentMetadata.grid.total_cells;
        statsSummary.textContent = `${totalFilled.toLocaleString("ru-RU")} ячеек • ${currentMetadata.stats.unique_photos_used} фото (${currentMetadata.image.width}×${currentMetadata.image.height}px)`;
        previewPlaceholder.style.display = "none";

        // Open in viewer
        viewer.open(`/output/mosaic.dzi?t=${timestamp || Date.now()}`);
        return true;
      }
    } catch (e) {
      console.warn("No mosaic found yet:", e);
    }
    previewPlaceholder.style.display = "flex";
    return false;
  }

  // Load project status
  async function loadProjectStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();

      if (data.target) {
        targetFilename.textContent = data.target.filename;
        targetMeta.textContent = `${data.target.size_mb} MB • ${data.target.extension.toUpperCase()}`;
        targetThumb.src = `/source/${data.target.filename}?t=${Date.now()}`;
      } else {
        targetFilename.textContent = "Портрет не найден";
        targetMeta.textContent = "Положите target.png в папку source/";
      }

      photosCountText.textContent = `${data.photos_count} фото найдено`;

      // Sync form with config
      if (data.config) {
        const grid = data.config.grid || {};
        const matching = data.config.matching || {};

        if (grid.columns) {
          inputCols.value = grid.columns;
          badgeCols.textContent = grid.columns;
        }
        if (grid.tile_render_size) {
          inputTileSize.value = grid.tile_render_size;
          badgeTileSize.textContent = `${grid.tile_render_size} px`;
        }
        if (matching.color_blend_ratio !== undefined) {
          const pct = Math.round(matching.color_blend_ratio * 100);
          inputBlend.value = pct;
          badgeBlend.textContent = `${pct}%`;
        }
        if (matching.skip_transparent !== undefined) {
          checkTransparent.checked = matching.skip_transparent;
        }
        if (matching.unique_only !== undefined) {
          checkUnique.checked = matching.unique_only;
        }
        if (matching.random_top_k) {
          inputTopK.value = matching.random_top_k;
          badgeTopK.textContent = matching.random_top_k;
        }
      }

      if (data.mosaic_ready) {
        await loadExistingMosaic();
      } else {
        previewPlaceholder.style.display = "flex";
      }

    } catch (err) {
      console.error("Status load error:", err);
    }
  }

  // Start Generation
  async function triggerGeneration() {
    if (isGenerating) return;
    isGenerating = true;

    btnGenerate.classList.add("busy");
    btnGenerate.disabled = true;
    btnGenerateText.textContent = "Сборка выполняется...";
    progressWrap.style.display = "flex";
    progressStep.textContent = "Запуск процесса...";
    progressPercent.textContent = "0%";
    progressFill.style.width = "0%";

    const payload = {
      columns: parseInt(inputCols.value, 10),
      tile_render_size: parseInt(inputTileSize.value, 10),
      color_blend_ratio: parseFloat(inputBlend.value) / 100.0,
      skip_transparent: checkTransparent.checked,
      unique_only: checkUnique.checked,
      random_top_k: parseInt(inputTopK.value, 10)
    };

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!data.ok) {
        alert(data.error || "Ошибка запуска генерации");
        resetGenerateButton();
        return;
      }

      // Start polling
      pollInterval = setInterval(pollProgress, 250);

    } catch (err) {
      alert("Ошибка сети при обращении к серверу: " + err);
      resetGenerateButton();
    }
  }

  async function pollProgress() {
    try {
      const res = await fetch("/api/progress");
      const state = await res.json();

      progressStep.textContent = state.step;
      progressPercent.textContent = `${state.percent}%`;
      progressFill.style.width = `${state.percent}%`;

      if (state.error) {
        clearInterval(pollInterval);
        alert("Ошибка при сборке мозаики:\n" + state.error);
        resetGenerateButton();
        return;
      }

      if (!state.busy && state.percent >= 100) {
        clearInterval(pollInterval);
        resetGenerateButton();
        progressStep.textContent = "Готово!";
        setTimeout(() => {
          progressWrap.style.display = "none";
        }, 1500);

        // Dynamically reload OpenSeadragon with the fresh mosaic!
        await loadExistingMosaic(state.timestamp);
      }
    } catch (e) {
      console.warn("Progress poll error:", e);
    }
  }

  function resetGenerateButton() {
    isGenerating = false;
    btnGenerate.classList.remove("busy");
    btnGenerate.disabled = false;
    btnGenerateText.textContent = "Собрать фотомозаику";
  }

  btnGenerate.addEventListener("click", triggerGeneration);
  if (btnPlaceholderGen) {
    btnPlaceholderGen.addEventListener("click", triggerGeneration);
  }

  // Open output folder in OS
  btnOpenFolder.addEventListener("click", async () => {
    try {
      await fetch("/api/open-folder");
    } catch (e) {
      console.error(e);
    }
  });

  // Init
  initViewer();
  loadProjectStatus();
});
