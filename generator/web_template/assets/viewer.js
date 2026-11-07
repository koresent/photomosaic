document.addEventListener("DOMContentLoaded", async () => {
  let metadata = window.MOSAIC_DATA || null;

  // i18n dictionaries (auto-selected by browser language)
  const I18N = {
    ru: {
      pageTitle: "Фотомозаика — Deep Zoom",
      stats: (cells, photos) => `${cells.toLocaleString("ru-RU")} ячеек • ${photos} фото`,
      inspectorTitle: "Фрагмент",
      inspectorPos: (col, cols, row, rows) => `Колонка ${col} из ${cols}, Ряд ${row} из ${rows}`,
      inspectorClose: "Закрыть",
      hint: "Приближайте колесом мыши или жестом • Кликните на фото для просмотра",
      btnZoomIn: "Приблизить",
      btnZoomOut: "Отдалить",
      btnHome: "Исходный масштаб",
      btnMinimap: "Карта навигации",
      loadingText: "Загрузка фотомозаики..."
    },
    en: {
      pageTitle: "Photomosaic — Deep Zoom",
      stats: (cells, photos) => `${cells.toLocaleString("en-US")} cells • ${photos} photos`,
      inspectorTitle: "Fragment",
      inspectorPos: (col, cols, row, rows) => `Column ${col} of ${cols}, Row ${row} of ${rows}`,
      inspectorClose: "Close",
      hint: "Scroll or pinch to zoom • Click any photo to inspect",
      btnZoomIn: "Zoom In",
      btnZoomOut: "Zoom Out",
      btnHome: "Reset View",
      btnMinimap: "Navigation Map",
      loadingText: "Loading photomosaic..."
    }
  };

  // Pure dynamic browser language detection
  const detectLanguage = () => {
    const navLangs = navigator.languages || [navigator.language || "en"];
    for (const lang of navLangs) {
      const code = (lang || "").toLowerCase();
      if (
        code.startsWith("ru") ||
        code.startsWith("be") ||
        code.startsWith("kk") ||
        code.startsWith("uk")
      ) {
        return "ru";
      }
      if (code.startsWith("en")) {
        return "en";
      }
    }
    return "ru";
  };

  const currentLang = detectLanguage();
  const t = I18N[currentLang] || I18N.ru;
  document.documentElement.lang = currentLang;
  document.title = t.pageTitle;

  // DOM Elements
  const loadingScreen = document.getElementById("loading-screen");
  const loadingText = document.getElementById("loading-text");
  const loadingBarFill = document.getElementById("loading-bar-fill");
  const loadingPercent = document.getElementById("loading-percent");

  const brandStats = document.getElementById("brand-stats");
  const inspectorCard = document.getElementById("inspector-card");
  const inspectorTitle = document.getElementById("inspector-title");
  const inspectorImg = document.getElementById("inspector-img");
  const inspectorFilename = document.getElementById("inspector-filename");
  const inspectorPos = document.getElementById("inspector-pos");
  const inspectorClose = document.getElementById("inspector-close");
  const interactionHint = document.getElementById("interaction-hint");
  const navWrapper = document.getElementById("navigator-wrapper");

  const btnZoomIn = document.getElementById("btn-zoom-in");
  const btnZoomOut = document.getElementById("btn-zoom-out");
  const btnHome = document.getElementById("btn-home");
  const btnMinimap = document.getElementById("btn-minimap");

  // Apply localized strings
  if (loadingText) loadingText.textContent = t.loadingText;
  if (inspectorTitle) inspectorTitle.textContent = t.inspectorTitle;
  if (inspectorClose) inspectorClose.setAttribute("aria-label", t.inspectorClose);
  if (interactionHint) interactionHint.textContent = t.hint;

  if (btnZoomIn) {
    btnZoomIn.title = t.btnZoomIn;
    btnZoomIn.setAttribute("aria-label", t.btnZoomIn);
  }
  if (btnZoomOut) {
    btnZoomOut.title = t.btnZoomOut;
    btnZoomOut.setAttribute("aria-label", t.btnZoomOut);
  }
  if (btnHome) {
    btnHome.title = t.btnHome;
    btnHome.setAttribute("aria-label", t.btnHome);
  }
  if (btnMinimap) {
    btnMinimap.title = t.btnMinimap;
    btnMinimap.setAttribute("aria-label", t.btnMinimap);
  }

  // Progress Bar Helper
  let currentProgress = 0;
  const setProgress = (percent) => {
    if (percent < currentProgress) return;
    currentProgress = Math.min(100, Math.round(percent));
    if (loadingBarFill) loadingBarFill.style.width = `${currentProgress}%`;
    if (loadingPercent) loadingPercent.textContent = `${currentProgress}%`;
    if (loadingScreen) loadingScreen.setAttribute("aria-valuenow", currentProgress);

    if (currentProgress >= 100) {
      setTimeout(() => {
        if (loadingScreen) {
          loadingScreen.classList.add("fade-out");
          setTimeout(() => loadingScreen.remove(), 450);
        }
      }, 200);
    }
  };

  // Initial progress: DOM is ready
  setProgress(15);

  // Load metadata if not bundled
  if (!metadata) {
    try {
      const res = await fetch("metadata/mosaic_info.json");
      if (res.ok) {
        metadata = await res.json();
      }
    } catch (e) {
      console.warn("Could not fetch mosaic metadata:", e);
    }
  }

  setProgress(35);

  if (brandStats && metadata && metadata.grid && metadata.stats) {
    const totalFilled = metadata.stats.filled_cells !== undefined ? metadata.stats.filled_cells : metadata.grid.total_cells;
    brandStats.textContent = t.stats(totalFilled, metadata.stats.unique_photos_used);
  }

  // Determine tileSource
  let tileSource = "mosaic.dzi";
  if (metadata && metadata.image && metadata.dzi) {
    tileSource = {
      Image: {
        xmlns: "http://schemas.microsoft.com/deepzoom/2008",
        Url: "mosaic_files/",
        Format: metadata.dzi.format || "jpg",
        Overlap: metadata.dzi.overlap || 1,
        TileSize: metadata.dzi.tileSize || 256,
        Size: {
          Width: metadata.image.width,
          Height: metadata.image.height
        }
      }
    };
  }

  // Initialize OpenSeadragon
  const viewer = OpenSeadragon({
    id: "openseadragon-view",
    prefixUrl: "",
    tileSources: tileSource,
    showNavigationControl: false,
    showNavigator: true,
    navigatorId: "navigator-view",
    navigatorAutoFade: false,
    animationTime: 0.8,
    blendTime: 0.15,
    springStiffness: 9.0,
    maxZoomPixelRatio: 3.5,
    minZoomImageRatio: 0.75,
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

  // Track tile loading progress
  let initialTilesLoaded = 0;
  const initialTilesGoal = 4; // Low-level tiles needed for full portrait

  viewer.addHandler("open", () => {
    setProgress(55);
  });

  viewer.addHandler("tile-loaded", () => {
    initialTilesLoaded++;
    const progress = 55 + Math.min(45, (initialTilesLoaded / initialTilesGoal) * 45);
    setProgress(progress);
  });

  viewer.addHandler("tile-drawing", () => {
    setProgress(100);
  });

  // Safety fallback for slow or cached network
  setTimeout(() => {
    setProgress(100);
  }, 3500);

  // Fade out interaction hint on first user interaction
  let hintFaded = false;
  const fadeHint = () => {
    if (!hintFaded && interactionHint) {
      hintFaded = true;
      interactionHint.classList.add("fade-out");
      setTimeout(() => interactionHint.remove(), 600);
    }
  };

  viewer.addHandler("canvas-drag", fadeHint);
  viewer.addHandler("canvas-scroll", fadeHint);

  // Inspector handlers
  const closeInspector = () => {
    if (inspectorCard) inspectorCard.style.display = "none";
  };

  if (inspectorClose) {
    inspectorClose.addEventListener("click", closeInspector);
  }

  // Click on tile to inspect photo
  viewer.addHandler("canvas-click", (event) => {
    fadeHint();
    if (!event.quick || !metadata) return;

    const viewportPoint = viewer.viewport.pointFromPixel(event.position);
    const imagePoint = viewer.viewport.viewportToImageCoordinates(viewportPoint);

    const tileSize = metadata.grid.tile_size;
    const cols = metadata.grid.columns;
    const rows = metadata.grid.rows;

    const col = Math.floor(imagePoint.x / tileSize);
    const row = Math.floor(imagePoint.y / tileSize);

    if (col >= 0 && col < cols && row >= 0 && row < rows) {
      const cellIndex = row * cols + col;
      const cell = metadata.cells && metadata.cells[cellIndex];

      if (cell && !cell.empty && cell.photo) {
        inspectorFilename.textContent = cell.photo;
        inspectorPos.textContent = t.inspectorPos(col + 1, cols, row + 1, rows);
        inspectorImg.src = `assets/thumbs/${cell.thumb}`;
        inspectorCard.style.display = "flex";
        return;
      }
    }

    closeInspector();
  });

  // On-screen HUD Controls
  if (btnZoomIn) {
    btnZoomIn.addEventListener("click", () => {
      fadeHint();
      viewer.viewport.zoomBy(1.6);
      viewer.viewport.applyConstraints();
    });
  }

  if (btnZoomOut) {
    btnZoomOut.addEventListener("click", () => {
      fadeHint();
      viewer.viewport.zoomBy(1 / 1.6);
      viewer.viewport.applyConstraints();
    });
  }

  if (btnHome) {
    btnHome.addEventListener("click", () => {
      fadeHint();
      viewer.viewport.goHome();
      closeInspector();
    });
  }

  if (btnMinimap && navWrapper) {
    btnMinimap.addEventListener("click", () => {
      fadeHint();
      const isMobile = window.innerWidth <= 640;
      if (isMobile) {
        navWrapper.classList.toggle("mobile-visible");
      } else {
        if (navWrapper.style.display === "none") {
          navWrapper.style.display = "block";
        } else {
          navWrapper.style.display = "none";
        }
      }
    });
  }
});
