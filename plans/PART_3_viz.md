# PART 3 — Cost API + Visualization Endpoints

## Objective
Build Plotly JSON chart endpoints for daily trend, hourly heatmap, service breakdown,
and the remaining cost aggregation views.

---

## App: `apps/visualizations/`

Each chart builder is a pure function: takes query params, queries DB, returns Plotly JSON dict.

### `chart_builders/daily_trend.py`
```python
def build_daily_trend(account_id=None, service=None, region=None,
                      start_date=None, end_date=None) -> dict:
    """
    Line chart: daily unblended_cost grouped by service.
    Returns Plotly {'data': [...], 'layout': {...}}.
    """
    qs = DailyCostAggregate.objects.all()
    if account_id: qs = qs.filter(linked_account_id=account_id)
    if service:    qs = qs.filter(service=service)
    if region:     qs = qs.filter(region=region)
    if start_date: qs = qs.filter(date__gte=start_date)
    if end_date:   qs = qs.filter(date__lte=end_date)

    df = pd.DataFrame(qs.values('date','service','unblended_cost'))
    # Pivot: one trace per service
    pivot = df.pivot_table(index='date', columns='service',
                           values='unblended_cost', aggfunc='sum').fillna(0)
    traces = [
        {'type': 'scatter', 'mode': 'lines+markers',
         'name': col, 'x': pivot.index.astype(str).tolist(),
         'y': pivot[col].tolist()}
        for col in pivot.columns
    ]
    return {
        'data': traces,
        'layout': {
            'title': 'Daily Cost by Service',
            'xaxis': {'title': 'Date'},
            'yaxis': {'title': 'USD'},
            'hovermode': 'x unified',
        }
    }
```

### `chart_builders/hourly_heatmap.py`
```python
def build_hourly_heatmap(account_id=None, service=None, region=None) -> dict:
    """
    Heatmap: hour-of-day (0-23) vs day-of-week (0=Mon...6=Sun).
    z = average unblended_cost.
    """
    qs = HourlyCostAggregate.objects.all()
    # apply filters ...
    df = pd.DataFrame(qs.values('hour','unblended_cost'))
    df['hour_of_day'] = pd.to_datetime(df['hour']).dt.hour
    df['day_of_week'] = pd.to_datetime(df['hour']).dt.dayofweek
    pivot = df.pivot_table(index='day_of_week', columns='hour_of_day',
                           values='unblended_cost', aggfunc='mean').fillna(0)
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    return {
        'data': [{'type': 'heatmap',
                  'z': pivot.values.tolist(),
                  'x': list(range(24)),
                  'y': [days[i] for i in pivot.index],
                  'colorscale': 'Blues'}],
        'layout': {'title': 'Average Hourly Cost (Hour × Day)',
                   'xaxis': {'title': 'Hour of Day'},
                   'yaxis': {'title': 'Day of Week'}}
    }
```

### `chart_builders/service_breakdown.py`
```python
def build_service_breakdown(billing_period: str, account_id=None) -> dict:
    """Stacked bar chart: date × service."""
```

### `chart_builders/ri_coverage.py`
```python
def build_ri_coverage(account_id: str, billing_period: str) -> dict:
    """
    Line chart: daily RI coverage % (DiscountedUsage / (Usage + DiscountedUsage))
    per instance family.
    """
```

### `chart_builders/forecast_chart.py`
```python
def build_forecast_chart(forecast_run_id: int) -> dict:
    """
    Line chart with actual cost + predicted cost + CI band (lower/upper).
    Anomaly markers overlaid.
    """
```

### `chart_builders/anomaly_chart.py`
```python
def build_anomaly_chart(account_id: str, service: str, region: str,
                        start: datetime, end: datetime) -> dict:
    """Time series of hourly cost with anomaly scatter markers overlaid."""
```

### `chart_builders/split_sunburst.py`
```python
def build_split_sunburst(rule_id: int, billing_period: str) -> dict:
    """
    Sunburst: (service → region → tenant) cost allocation.
    """
```

### `views.py`
```python
class DailyTrendView(APIView):
    def get(self, request):
        params = {
            'account_id': request.query_params.get('account_id'),
            'service':    request.query_params.get('service'),
            'region':     request.query_params.get('region'),
            'start_date': request.query_params.get('start_date'),
            'end_date':   request.query_params.get('end_date'),
        }
        return Response(build_daily_trend(**params))

# Same pattern for each chart builder
```

### `urls.py`
```python
urlpatterns = [
    path('daily-trend/',       DailyTrendView.as_view()),
    path('hourly-heatmap/',    HourlyHeatmapView.as_view()),
    path('service-breakdown/', ServiceBreakdownView.as_view()),
    path('ri-coverage/',       RiCoverageView.as_view()),
    path('forecast-chart/',    ForecastChartView.as_view()),
    path('anomaly-chart/',     AnomalyChartView.as_view()),
    path('split-sunburst/',    SplitSunburstView.as_view()),
]
```

---

## Additional Cost API Views

These belong in `apps/costs/views.py`:

**`TopNCostView`** (`GET /api/v1/costs/top-n/`)
```python
# ?n=10&group_by=usage_type&billing_period=2025-01
qs = (LineItem.objects
      .filter(billing_period=billing_period)
      .values(group_by)
      .annotate(total=Sum('unblended_cost'))
      .order_by('-total')[:n])
```

**`CostByTagView`** (`GET /api/v1/costs/by-tag/`)
```python
# ?tag_key=user:team&billing_period=2025-01
# Uses JSONB containment: tags__has_key=tag_key
# Returns total cost per unique tag value
```

---

## Verification
```bash
# With fake data loaded from Part 2:
curl "http://localhost:8000/api/v1/viz/daily-trend/?start_date=2025-01-01&end_date=2025-01-31"
# → {"data": [...31 date points per service...], "layout": {...}}

curl "http://localhost:8000/api/v1/viz/hourly-heatmap/"
# → {"data": [{"type": "heatmap", "z": [[...24 cols...], ...7 rows...], ...}], "layout": {...}}

curl "http://localhost:8000/api/v1/costs/top-n/?n=5&group_by=service&billing_period=2025-01"
# → top 5 services by cost
```

---

## NEXT

After completing Part 3, run:
**`/Users/mfeldman/.claude/plans/PART_4_pricing_datasets.md`**
