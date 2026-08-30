from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.core.config import Settings, get_settings
from app.services.file_service import FileReadError, FileService, StoredFile
from app.services.registry_runtime import RegistryRuntime


logger = logging.getLogger(__name__)


# Палитры categorical-стилей (исторические цвета APL-UI).
PIE_PALETTE = [
    "#d06b4e", "#114b5f", "#6c8b6b", "#8d3f28", "#c9a86a",
    "#7a6c8d", "#3e7cb3", "#b6542f", "#5a8a5a", "#8a5a8a",
]
BAR_COLOR = "#6c8b6b"
LINE_COLOR = "#114b5f"
HIST_COLOR = "#d06b4e"
HIST_EDGE = "#8d3f28"


class ChartService:
    """Рендер графиков — декларативный (Вариант 4: chart spec как данные).

    Тип графика — запись runtime-реестра (`registry_runtime.RegistryRuntime`)
    с рецептом; здесь — три generic-исполнителя по `recipe.kind`:
      histogram   — распределение числовой колонки;
      categorical — dimension × numeric с агрегацией (style bar|pie);
      timeline    — datetime × numeric точки.
    Выбор осей по умолчанию выражен данными (`x_role`/`y_role` рецепта) —
    исторические дефолты четырёх базовых типов закодированы в сиде реестра
    (registries.py) и сохранены 1:1.
    """

    def __init__(self, file_service: FileService, settings: Settings | None = None) -> None:
        self.file_service = file_service
        self.settings = settings or get_settings()
        self.registry = RegistryRuntime(self.settings)

    def generate_chart(
        self,
        stored_file: StoredFile,
        chart_type: str,
        x_column: str | None = None,
        y_column: str | None = None,
    ) -> dict[str, Any]:
        chart_type = chart_type.lower()
        known = self.registry.chart_types_set()
        if chart_type not in known:
            raise FileReadError(f"Поддерживаются только графики: {', '.join(sorted(known))}.")

        self.file_service.ensure_storage()
        if stored_file.kind == "table":
            chart = self._generate_table_chart(stored_file, chart_type, x_column, y_column)
        else:
            chart = self._generate_image_chart(stored_file, chart_type)

        logger.info("Generated %s chart for %s", chart_type, stored_file.file_id)
        return chart

    def generate_default_charts(self, stored_file: StoredFile) -> list[dict[str, Any]]:
        charts: list[dict[str, Any]] = []
        for chart_type in self.registry.chart_type_keys()[:2]:
            try:
                charts.append(self.generate_chart(stored_file, chart_type))
            except FileReadError:
                continue
        return charts

    # --- табличные данные: декларативный рендер ---

    def _generate_table_chart(
        self,
        stored_file: StoredFile,
        chart_type: str,
        x_column: str | None,
        y_column: str | None,
    ) -> dict[str, Any]:
        recipe = self.registry.chart_recipe(chart_type)
        kind = recipe["kind"]

        dataframe = self.file_service.read_dataframe(stored_file)
        columns = self.file_service.describe_columns(dataframe)
        roles = {
            "numeric": [item["name"] for item in columns if item["kind"] == "numeric"],
            "dimension": [
                item["name"] for item in columns if item["kind"] in ("categorical", "datetime")
            ],
            "datetime": [item["name"] for item in columns if item["kind"] == "datetime"],
            "any": list(dataframe.columns),
        }

        try:
            if kind == "histogram":
                rendered = self._render_histogram(recipe, dataframe, roles, x_column)
            elif kind == "timeline":
                rendered = self._render_timeline(
                    recipe, chart_type, dataframe, roles, x_column, y_column
                )
            else:
                rendered = self._render_categorical(
                    recipe, chart_type, dataframe, roles, x_column, y_column
                )
            rendered_figure, description = rendered
        except Exception:
            plt.close("all")
            raise

        file_name = self._build_output_name(stored_file.file_id, chart_type, "png")
        output_path = self.settings.output_dir / file_name
        rendered_figure.tight_layout()
        rendered_figure.savefig(output_path, bbox_inches="tight")
        plt.close(rendered_figure)
        return {
            "title": f"{chart_type.title()} chart",
            "description": description,
            "file_name": file_name,
            "relative_path": f"outputs/{file_name}",
            "storage_url": f"/storage/outputs/{file_name}",
            "download_url": f"/download/{file_name}",
        }

    def _resolve_column(
        self,
        roles: dict[str, list[str]],
        role: str,
        explicit: str | None,
        fallback_role: str | None,
    ) -> str | None:
        """Колонка по роли: явная → первая колонок роли → fallback-роль → None."""
        if explicit:
            return explicit
        if roles.get(role):
            return roles[role][0]
        if fallback_role and roles.get(fallback_role):
            return roles[fallback_role][0]
        return None

    def _render_histogram(
        self,
        recipe: dict[str, Any],
        dataframe: pd.DataFrame,
        roles: dict[str, list[str]],
        x_column: str | None,
    ) -> tuple[Any, str]:
        selected_x = self._resolve_column(
            roles, recipe.get("x_role", "numeric"), x_column, fallback_role="numeric"
        )
        if selected_x is None:
            raise FileReadError("Для histogram нужен хотя бы один числовой столбец.")
        series = pd.to_numeric(dataframe[selected_x], errors="coerce").dropna()
        if series.empty:
            raise FileReadError("Недостаточно числовых значений для histogram.")
        bins = recipe.get("bins") or min(20, max(8, int(np.sqrt(len(series)))))
        figure, axis = self._new_figure()
        axis.hist(series, bins=int(bins), color=HIST_COLOR, edgecolor=HIST_EDGE)
        axis.set_title(f"Histogram: {selected_x}")
        axis.set_xlabel(selected_x)
        axis.set_ylabel("Frequency")
        return figure, f"Распределение значений колонки «{selected_x}»."

    def _render_timeline(
        self,
        recipe: dict[str, Any],
        chart_type: str,
        dataframe: pd.DataFrame,
        roles: dict[str, list[str]],
        x_column: str | None,
        y_column: str | None,
    ) -> tuple[Any, str]:
        line_x = self._resolve_column(
            roles, recipe.get("x_role", "datetime"), x_column, fallback_role="dimension"
        )
        if line_x is None:
            raise FileReadError(f"Для {chart_type} не найдена подходящая ось X (datetime/размерность).")
        selected_y = self._resolve_column(
            roles, recipe.get("y_role", "numeric"), y_column, fallback_role="numeric"
        )
        if selected_y is None:
            raise FileReadError(f"Для {chart_type} нужен хотя бы один числовой столбец.")
        if selected_y not in dataframe.columns:
            raise FileReadError(f"Колонка «{selected_y}» не найдена в файле.")

        plot_frame = dataframe[[line_x, selected_y]].copy()
        plot_frame[selected_y] = pd.to_numeric(plot_frame[selected_y], errors="coerce")
        plot_frame = plot_frame.dropna(subset=[selected_y]).head(int(recipe.get("limit", 50)))
        if plot_frame.empty:
            raise FileReadError(f"Недостаточно данных для {chart_type} графика.")
        figure, axis = self._new_figure()
        axis.plot(
            plot_frame[line_x].astype(str),
            plot_frame[selected_y],
            color=LINE_COLOR,
            linewidth=2.5,
            marker="o",
        )
        axis.set_title(f"Line chart: {selected_y} by {line_x}")
        axis.set_xlabel(line_x)
        axis.set_ylabel(selected_y)
        axis.tick_params(axis="x", rotation=35)
        return figure, f"Линейная динамика «{selected_y}» по оси «{line_x}»."

    def _render_categorical(
        self,
        recipe: dict[str, Any],
        chart_type: str,
        dataframe: pd.DataFrame,
        roles: dict[str, list[str]],
        x_column: str | None,
        y_column: str | None,
    ) -> tuple[Any, str]:
        style = recipe.get("style", "bar")
        agg = recipe.get("agg", "mean")
        top_n = int(recipe.get("top_n", 10))
        selected_x = self._resolve_column(
            roles, recipe.get("x_role", "dimension"), x_column, fallback_role="any"
        )
        if selected_x is None:
            raise FileReadError(f"Недостаточно данных для {chart_type} графика.")
        selected_y = self._resolve_column(
            roles, recipe.get("y_role", "numeric"), y_column, fallback_role="numeric"
        )

        # Исторический fallback: без числовой колонки (или agg=count)
        # categorical-тип строит частоты по колонке-размерности.
        frequency_mode = agg == "count" or selected_y is None or not roles["numeric"]
        grouped = self._aggregate(
            dataframe,
            selected_x,
            None if frequency_mode else selected_y,
            agg if not frequency_mode else "count",
            top_n,
        )
        if grouped.empty:
            raise FileReadError(f"Недостаточно данных для {chart_type} графика.")

        figure, axis = self._new_figure()
        if style == "pie":
            axis.pie(
                grouped.values,
                labels=grouped.index.astype(str),
                autopct="%1.1f%%",
                startangle=90,
                colors=PIE_PALETTE[: len(grouped)],
            )
            axis.set_title(f"Pie chart: {selected_x}")
            axis.axis("equal")
            if frequency_mode:
                return figure, f"Доли по категориям «{selected_x}» (частоты)."
            return figure, f"Доли «{selected_y}» по категориям «{selected_x}» ({agg})."

        axis.bar(grouped.index.astype(str), grouped.values, color=BAR_COLOR)
        axis.set_ylabel("Count" if frequency_mode else f"{agg.capitalize()} {selected_y}")
        axis.set_title(f"Bar chart: {selected_x}")
        axis.tick_params(axis="x", rotation=30)
        if frequency_mode:
            return figure, f"Частоты по колонке «{selected_x}»."
        agg_label = {"mean": "Средние значения", "sum": "Суммы", "count": "Частоты"}[agg]
        return figure, f"{agg_label} «{selected_y}» по категориям «{selected_x}» ({agg})."

    def _aggregate(
        self,
        dataframe: pd.DataFrame,
        x_column: str,
        y_column: str | None,
        agg: str,
        top_n: int,
    ) -> pd.Series:
        """freq (count без y) или groupby-агрегация y по x, топ-N по убыванию."""
        if y_column is None or agg == "count":
            return dataframe[x_column].astype(str).value_counts().head(top_n)
        grouped = (
            dataframe[[x_column, y_column]]
            .copy()
            .dropna(subset=[x_column, y_column])
            .groupby(x_column, dropna=True)[y_column]
            .agg(agg)
            .sort_values(ascending=False)
            .head(top_n)
        )
        return grouped

    def _new_figure(self):
        figure, axis = plt.subplots(figsize=(10, 5.8), dpi=150)
        figure.patch.set_facecolor("#f8f3ea")
        axis.set_facecolor("#fffaf3")
        return figure, axis

    # --- изображения (kind файла, не тип реестра) ---

    def _generate_image_chart(self, stored_file: StoredFile, chart_type: str) -> dict[str, Any]:
        image = self.file_service.open_image(stored_file)
        array = np.array(image)
        grayscale = np.array(image.convert("L"))
        file_name = self._build_output_name(stored_file.file_id, chart_type, "png")
        output_path = self.settings.output_dir / file_name

        figure, axis = self._new_figure()

        if chart_type == "histogram":
            axis.hist(grayscale.ravel(), bins=32, color=HIST_COLOR, edgecolor=HIST_EDGE)
            axis.set_title("Pixel intensity histogram")
            axis.set_xlabel("Intensity")
            axis.set_ylabel("Pixels")
            description = "Распределение интенсивности пикселей изображения."
        elif chart_type == "bar":
            if array.ndim == 2:
                labels = ["L"]
                values = [grayscale.mean()]
                colors = ["#114b5f"]
            else:
                labels = list(image.getbands())
                values = [array[:, :, index].mean() for index in range(array.shape[2])]
                colors = ["#114b5f", BAR_COLOR, HIST_COLOR, "#8d3f28"][: len(labels)]
            axis.bar(labels, values, color=colors)
            axis.set_title("Mean channel values")
            axis.set_ylabel("Average value")
            description = "Средние значения по каналам изображения."
        elif chart_type == "pie":
            if array.ndim == 2:
                labels = ["L"]
                values = [grayscale.mean()]
            else:
                labels = list(image.getbands())
                values = [array[:, :, index].mean() for index in range(array.shape[2])]
            axis.pie(
                values,
                labels=labels,
                autopct="%1.1f%%",
                startangle=90,
                colors=PIE_PALETTE[: len(labels)],
            )
            axis.set_title("Channel share (mean values)")
            axis.axis("equal")
            description = "Доли средних значений по каналам изображения."
        else:
            profile = grayscale.mean(axis=0)
            axis.plot(np.arange(len(profile)), profile, color=LINE_COLOR, linewidth=2.0)
            axis.set_title("Horizontal brightness profile")
            axis.set_xlabel("X coordinate")
            axis.set_ylabel("Average brightness")
            description = "Средняя яркость по горизонтальной оси изображения."

        figure.tight_layout()
        figure.savefig(output_path, bbox_inches="tight")
        plt.close(figure)
        return {
            "title": f"{chart_type.title()} chart",
            "description": description,
            "file_name": file_name,
            "relative_path": f"outputs/{file_name}",
            "storage_url": f"/storage/outputs/{file_name}",
            "download_url": f"/download/{file_name}",
        }

    def _build_output_name(self, file_id: str, artifact_type: str, extension: str) -> str:
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
        return f"{file_id}__{artifact_type}__{timestamp}.{extension}"