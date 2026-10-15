from django.shortcuts import render, redirect
import matplotlib
from django.http import HttpResponse, JsonResponse
from matplotlib.backends.backend_pdf import PdfPages
from django.contrib.auth.hashers import check_password, make_password
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import io
import os
import base64
import json
import threading
from .models import login_data
from django.contrib import messages
from django.contrib.auth.decorators import login_required

_plot_lock = threading.Lock()
BAR_COLOR = '#1f4e79'
MAX_CATEGORIES = 200

OUTPUT_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}


#Charts
def _set_category_ticks(ax, labels, max_ticks=20):
    n = len(labels)
    step = max(1, -(-n // max_ticks))
    ticks = list(range(0, n, step))
    rotate = n > 8
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(labels[i]) for i in ticks],
    rotation=45 if rotate else 0,
    ha='right' if rotate else 'center')

def get_line_plot(x, y, title, xlabel, ylabel, figsize=(8, 5), dpi=100):
    if len(x) != len(y):
        raise ValueError(f"x and y must be same length, got {len(x)} vs {len(y)}")
    if len(x) == 0:
        raise ValueError("x and y cannot be empty")

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.plot(range(len(x)), y, marker='o' if len(x) <= 60 else None, linestyle='-', color=BAR_COLOR)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    _set_category_ticks(ax, x)

    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)

    graph_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    buffer.close()
    return graph_base64

def get_bar_plot(x, y, title, xlabel, ylabel, figsize=(8, 5), dpi=100):
    if len(x) != len(y):
        raise ValueError(f"x and y must be same length, got {len(x)} vs {len(y)}")
    if len(x) == 0:
        raise ValueError("x and y cannot be empty")

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.bar(range(len(x)), y, color=BAR_COLOR)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    _set_category_ticks(ax, x)
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)

    graph_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    buffer.close()
    return graph_base64

def get_pie_chart(labels, values, title, figsize=(8, 5), dpi=100):
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    ax.set_title(title)

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)

    graph_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    buffer.close()
    return graph_base64

def get_scatter_plot(x, y, title, xlabel, ylabel, color='darkorange', figsize=(8, 5), dpi=100):
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.scatter(x, y, color=color, alpha=0.7, edgecolors='black')
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)

    graph_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    buffer.close()
    return graph_base64

#Page Views

def loginpage(request):
    if request.method == "POST":
        name = request.POST.get("username")
        password = request.POST.get("password")

        try:
            user = login_data.objects.get(name=name)

            if user.password == password:
                request.session['name'] = user.name
                return redirect("import_file")
            else:
                return render(request, "login.html", {"error": "Wrong password"})
        except login_data.DoesNotExist:
            return render(request, "login.html", {"error": "User not found"})

    return render(request, "login.html")

def convert_page(request):
    return render(request, "convert.html")

def clean(request):
    context = {}

    grade_data = request.session.get("grade_data")
    file_name = request.session.get("file_name")
    date_cols = request.session.get("date_cols", [])

    if not grade_data:
        context['error'] = "No uploaded file found. Please upload a file first."
        return render(request, 'clean.html', context)

    df = pd.read_json(io.StringIO(grade_data), orient="records")

    cols_to_restore = date_cols if date_cols else [c for c in df.columns if 'date' in c.lower()]
    for col in cols_to_restore:
        if col in df.columns:
            try:
                df[col] = pd.to_datetime(df[col], unit='ms')
            except (ValueError, TypeError):
                pass

    context['file_name'] = file_name
    context['original_shape'] = f"{df.shape[0]} rows × {df.shape[1]} columns"
    context['columns'] = list(df.columns)

    if request.method == 'POST':
        options = request.POST.getlist('clean_options')

        try:
            if 'strip_whitespace' in options:
                str_cols = df.select_dtypes(include='object').columns
                df[str_cols] = df[str_cols].apply(lambda col: col.str.strip())

            if 'drop_duplicates' in options:
                df = df.drop_duplicates()

            if 'drop_empty_rows' in options:
                df = df.dropna(how='all')

            if 'drop_empty_cols' in options:
                df = df.dropna(axis=1, how='all')

            if 'fill_missing_zero' in options:
                num_cols = df.select_dtypes(include='number').columns
                df[num_cols] = df[num_cols].fillna(0)

            if 'fill_missing_mean' in options:
                num_cols = df.select_dtypes(include='number').columns
                df[num_cols] = df[num_cols].fillna(df[num_cols].mean())

            if 'drop_missing_rows' in options:
                df = df.dropna()

            if 'standardize_headers' in options:
                df.columns = [
                    str(c).strip().lower().replace(' ', '_') for c in df.columns
                ]

        except Exception as e:
            context['error'] = f"Something went wrong while cleaning: {e}"
            context['preview'] = df.head(10).to_html(classes='preview-table', index=False)
            return render(request, 'clean.html', context)

        request.session["grade_data"] = df.to_json(orient="records")
        context['cleaned_shape'] = f"{df.shape[0]} rows × {df.shape[1]} columns"
        context['applied'] = options
        context['success'] = "Cleaning applied and saved."

    context['preview'] = df.head(10).to_html(classes='preview-table', index=False, na_rep='—')

    return render(request, 'clean.html', context)

def download_clean(request):
    data_json = request.session.get("grade_data")

    if not data_json:
        return redirect('import_file')

    df = pd.read_json(io.StringIO(data_json), orient="records")

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="cleaned_data.xlsx"'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    return response

def import_file(request):
    context = {}

    if request.method == 'POST' and request.FILES.get('uploaded_file'):
        uploaded_file = request.FILES['uploaded_file']
        filename = uploaded_file.name.lower()

        if filename.endswith('.xlsx'):
            try:
                df = pd.read_excel(uploaded_file, engine='openpyxl')
            except Exception as e:
                context['error'] = f"Something went wrong while processing the file: {e}"
                return render(request, 'import.html', context)

        elif filename.endswith('.json'):
            try:
                df = pd.read_json(uploaded_file, orient='records')
            except Exception as e:
                context['error'] = f"Something went wrong while processing the file: {e}"
                return render(request, 'import.html', context)

        elif filename.endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file)
            except Exception as e:
                context['error'] = f"Something went wrong while processing the file: {e}"
                return render(request, 'import.html', context)

        else:
            context['error'] = "Unsupported file type. Please upload a .xlsx or .csv file."
            return render(request, 'import.html', context)

        if df.empty or len(df.columns) == 0:
            context['error'] = "The uploaded file appears to be empty or has no columns."
            return render(request, 'import.html', context)

        request.session["grade_data"] = df.to_json(orient="records")
        request.session["file_name"] = uploaded_file.name

        return redirect('visualize')   

    return render(request, 'import.html')

def get_suggested_comparisons(df, max_suggestions=10):
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include="object").columns.tolist()

    suggestions = []

    if len(numeric_cols) >= 2:
        corr = df[numeric_cols].corr().abs()
        for i, col_a in enumerate(numeric_cols):
            for col_b in numeric_cols[i + 1:]:
                score = corr.loc[col_a, col_b]
                if pd.notna(score):
                    chart = "scatter" if score < 0.8 else "line"
                    suggestions.append({
                        "x": col_a,
                        "y": col_b,
                        "label": f"{col_b} vs {col_a} (corr: {score:.2f})",
                        "chart_type": chart,
                        "score": score,
                    })

    for cat_col in categorical_cols:
        if df[cat_col].nunique() > 15 or df[cat_col].nunique() < 2:
            continue

        for num_col in numeric_cols:
            group_means = df.groupby(cat_col)[num_col].mean()
            overall_mean = df[num_col].mean()

            if overall_mean == 0 or pd.isna(overall_mean):
                continue

            spread = group_means.std() / abs(overall_mean)

            if pd.notna(spread) and spread > 0:
                chart = "pie" if df[cat_col].nunique() <= 6 else "bar"
                suggestions.append({
                    "x": cat_col,
                    "y": num_col,
                    "label": f"{num_col} by {cat_col} (spread: {spread:.2f})",
                    "chart_type": chart,
                    "score": spread,
                })

    suggestions.sort(key=lambda s: s["score"], reverse=True)
    return suggestions[:max_suggestions]


def build_chart_image(payload):
    """Draw one chart with matplotlib from the data the page already prepared.
    Returns a base64 PNG string."""
    chart_type = payload.get("type")
    x_label = str(payload.get("x") or "")
    y_label = str(payload.get("y") or "Count")
    title = str(payload.get("title") or (f"{y_label} by {x_label}" if x_label else ""))
    dpi = 150

    with _plot_lock:
        if chart_type == "scatter":
            points = payload.get("points") or []
            if not points:
                raise ValueError("No points to plot.")
            xs = [float(p["x"]) for p in points]
            ys = [float(p["y"]) for p in points]
            return get_scatter_plot(xs, ys, title, x_label, y_label, color=BAR_COLOR, dpi=dpi)

        labels = [str(v) for v in (payload.get("labels") or [])]
        values = [float(v) for v in (payload.get("values") or [])]
        if not labels or len(labels) != len(values):
            raise ValueError("No data to plot.")

        if chart_type == "line":
            return get_line_plot(labels, values, title, x_label, y_label, dpi=dpi)

        if len(labels) > MAX_CATEGORIES:
            raise ValueError(
                f"Too many categories ({len(labels)}). Pick a column with fewer "
                f"than {MAX_CATEGORIES} distinct values, or use a line chart."
            )
        if chart_type == "pie":
            if any(v < 0 for v in values) or sum(values) <= 0:
                raise ValueError("Pie charts need non-negative values with a total above zero.")
            return get_pie_chart(labels, values, title, dpi=dpi)
        if chart_type == "bar":
            return get_bar_plot(labels, values, title, x_label, y_label, dpi=dpi)

    raise ValueError(f"Unknown chart type: {chart_type}")


def visualize(request):
    data_json = request.session.get("grade_data")

    if request.method == 'POST':
        if not data_json:
            return JsonResponse({"error": "Session expired. Please upload the file again."}, status=400)
        try:
            image = build_chart_image(json.loads(request.body))
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"image": image})

    if not data_json:
        return redirect('import_file')

    df = pd.read_json(io.StringIO(data_json), orient="records")

    records = df.astype(object).where(df.notna(), None).to_dict(orient="records")

    suggestions = [
        {k: v for k, v in s.items() if k != "score"}
        for s in get_suggested_comparisons(df)
    ]

    context = {
        "data": records,
        "total_rows": len(df),
        "columns": df.columns.tolist(),
        "file_name": request.session.get("file_name"),
        "suggestions": suggestions,
    }
    return render(request, 'visualize.html', context)

#Conversion Pages

def convert(request):
    if request.method != "POST":
        return render(request, "convert.html")
 
    uploaded = request.FILES.get("uploaded_file")
    target = request.POST.get("output_format")
 
    if not uploaded:
        return render(request, "convert.html", {"error": "Choose a file to convert."})
    if target not in OUTPUT_TYPES:
        return render(request, "convert.html", {"error": "Choose a format to convert to."})
 
    base_name, ext = os.path.splitext(uploaded.name)
    ext = ext.lower()
 
    # Read the uploaded file into a DataFrame
    try:
        if ext == ".csv":
            df = pd.read_csv(uploaded)
        elif ext == ".xlsx":
            df = pd.read_excel(uploaded)
        elif ext == ".json":
            df = pd.read_json(uploaded)
        else:
            return render(request, "convert.html",
                {"error": "Unsupported file type. Use .xlsx, .csv or .json."})
    except Exception:
        return render(request, "convert.html",
            {"error": "That file could not be read. Check that it is a valid " + ext + " file."})
 
    # Write it out in the chosen format
    if target == "csv":
        content = df.to_csv(index=False).encode("utf-8-sig")  # utf-8-sig so Excel reads accents correctly
    elif target == "xlsx":
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        content = buffer.getvalue()
    else:  # json
        content = df.to_json(orient="records", indent=2, force_ascii=False).encode("utf-8")
 
    response = HttpResponse(content, content_type=OUTPUT_TYPES[target])
    response["Content-Disposition"] = f'attachment; filename="{base_name}.{target}"'
    return response

def create_user(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        if not username or not password:
            messages.error(request, "All fields are required.")
            return redirect("createuser")

        if login_data.objects.filter(name__iexact=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("createuser")

        login_data.objects.create(
            name=username,
            password=password,
        )

        messages.success(request, "Account created successfully!")
        return redirect("createuser")

    users = login_data.objects.only("empid", "name", "password").order_by("empid")
    return render(request, "createuser.html", {"users": users})

def homepage(request):
    return render(request, "homepage.html")