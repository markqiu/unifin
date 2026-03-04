"""开放式基金净值数据 — data model."""

import datetime as dt

from pydantic import BaseModel, Field, model_validator

from unifin.core.registry import ModelInfo, model_registry


class FundNavQuery(BaseModel):
    """Query parameters for 开放式基金净值数据."""

    symbol: str = Field(
        default=...,
        description="基金代码",
    )
    start_date: dt.date | None = Field(
        default=None,
        description="开始日期",
    )
    end_date: dt.date | None = Field(
        default=None,
        description="结束日期",
    )

    @model_validator(mode="after")
    def _validate_dates(self) -> "FundNavQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            from unifin.core.errors import InvalidDateRangeError

            raise InvalidDateRangeError(self.start_date, self.end_date)
        return self


class FundNavData(BaseModel):
    """Result schema for 开放式基金净值数据."""

    date: dt.date = Field(
        description="净值日期",
    )
    nav: float | None = Field(
        default=None,
        description="单位净值",
    )
    acc_nav: float | None = Field(
        default=None,
        description="累计净值",
    )
    daily_return: float | None = Field(
        default=None,
        description="日收益率（单位：%）",
    )
    symbol: str | None = Field(
        default=None,
        description="基金代码",
    )
    name: str | None = Field(
        default=None,
        description="基金名称",
    )


# ── Register the model ──
model_registry.register(
    ModelInfo(
        name="fund_nav",
        category="fund.price",
        query_type=FundNavQuery,
        result_type=FundNavData,
        description="开放式基金净值数据",
    )
)
