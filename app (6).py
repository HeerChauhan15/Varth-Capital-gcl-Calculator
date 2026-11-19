import streamlit as st
import pandas as pd
import os
import re
import io

BRAND = "Varth Capital GCL Premium Calculator"

st.set_page_config(
    page_title=f"{BRAND} – Premium Calculator",
    page_icon="💰",
    layout="wide"
)

st.title(f"💰 {BRAND}")
st.markdown("### Premium Calculator")
st.markdown("Select plan details below")

# GST is fixed and always applied on top of the premium.
GST_RATE_FIXED = 18.0

# ============================================
# SEGMENT CONFIG  (only 3 segments)
# "file" = Excel file name in the GitHub repo (extension optional-tolerant).
# The first sheet of each file is used for rates.
# ============================================
SEGMENTS = {
    "Vehicle Loan": {
        "file": "Vechile.xlsx",
        "sa_min": 25000, "sa_max": 500000, "t_min": 2, "t_max": 5,
    },
    "LAP": {
        "file": "LAP.xlsx",
        "sa_min": 50000, "sa_max": 4000000, "t_min": 2, "t_max": 10,
    },
    "Personal Loan": {
        "file": "PL.xlsx",
        "sa_min": 25000, "sa_max": 3000000, "t_min": 2, "t_max": 5,
    },
}

AGE_MIN, AGE_MAX = 18, 65


# ============================================
# PREMIUM FORMULA (no loader):
#   Premium (Excl. GST) = Base Rate x (Sum Assured / 1,00,000)
#   GST Amount          = Premium (Excl. GST) x (GST% / 100)
#   Premium (Incl. GST) = Premium (Excl. GST) + GST Amount
# ============================================
def compute_premium_breakdown(base_rate, sum_assured, gst_pct=GST_RATE_FIXED):
    premium_excl_gst = round(base_rate * (sum_assured / 100000.0))
    gst_amount = round(premium_excl_gst * (gst_pct / 100.0), 2)
    premium_incl_gst = round(premium_excl_gst + gst_amount, 2)
    return premium_excl_gst, gst_amount, premium_incl_gst


def _norm_name(s):
    return re.sub(r"\s+", "", str(s)).lower()


def resolve_file(fname):
    """Exact match first; otherwise ignore spaces/case, and also accept the
    name without extension (so 'LAP' / 'LAP.xlsx' / 'lap.xls' all work)."""
    if os.path.exists(fname):
        return fname
    target = _norm_name(fname)
    target_base = os.path.splitext(target)[0]
    for f in os.listdir("."):
        n = _norm_name(f)
        if n == target or os.path.splitext(n)[0] == target_base:
            if f.lower().endswith((".xlsx", ".xls", ".xlsm")):
                return f
    return None


def load_rate_table(loan_type):
    fname = SEGMENTS[loan_type]["file"]
    path = resolve_file(fname)
    if path is None:
        raise FileNotFoundError(
            f"File not found: '{fname}' — Please make sure this file is in the GitHub repo."
        )

    sheet = 0  # first sheet of the file
    raw = pd.read_excel(path, sheet_name=sheet, header=None)

    header_row = None
    for i, row in raw.iterrows():
        for val in row.values:
            if isinstance(val, str) and "AGE" in val.upper():
                header_row = i
                break
        if header_row is not None:
            break

    if header_row is None:
        raise ValueError("Could not find AGE/TERM header row in the file.")

    df = pd.read_excel(path, sheet_name=sheet, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    age_col = df.columns[0]
    df = df.dropna(subset=[age_col])
    df[age_col] = pd.to_numeric(df[age_col], errors='coerce')
    df = df.dropna(subset=[age_col])
    df[age_col] = df[age_col].astype(int)
    df = df.set_index(age_col)

    tenure_map = {}
    for col in df.columns:
        try:
            tenure_map[int(float(col))] = col
        except Exception:
            pass

    return df, tenure_map


def get_rate(df, tenure_map, age, tenure):
    if age not in df.index:
        raise ValueError(f"Age {age} not found in rate table.")
    if tenure not in tenure_map:
        raise ValueError(f"Tenure {tenure} yrs not found in rate table.")
    return float(df.loc[age, tenure_map[tenure]])


def find_column(df, target):
    target_norm = target.strip().lower().replace(" ", "")
    for col in df.columns:
        col_norm = str(col).strip().lower().replace(" ", "")
        if col_norm == target_norm:
            return col
    return None


def find_sum_assured_columns(df):
    """Detects Sum Assured/Sum Insured column and Loan Outstanding column.
    Per row, Sum Assured is used; if blank, Loan Outstanding is the fallback."""
    sa_col = None
    lo_col = None
    for col in df.columns:
        norm = re.sub(r'[\s_\-/]+', '', str(col).lower())
        if sa_col is None and ('sumassured' in norm or 'suminsured' in norm):
            sa_col = col
        if lo_col is None and ('loanoutstanding' in norm or 'outstandingamount' in norm or 'outstandingloan' in norm
                or norm == 'outstanding' or 'loanos' in norm or norm == 'os'):
            lo_col = col
    return sa_col, lo_col


# ============================================
# DROPDOWNS
# ============================================
col1, _ = st.columns([1, 1])
with col1:
    loan_type = st.selectbox("Select Loan Type", list(SEGMENTS.keys()))

cfg = SEGMENTS[loan_type]
sa_min, sa_max = cfg["sa_min"], cfg["sa_max"]
min_tenure, max_tenure = cfg["t_min"], cfg["t_max"]

st.caption(
    f"**{loan_type}** — "
    f"Sum Assured ₹{sa_min:,} – ₹{sa_max:,} · Tenure {min_tenure} – {max_tenure} yrs · "
    f"Age {AGE_MIN} – {AGE_MAX}"
)

st.divider()

# ============================================
# MANUAL SECTION
# Inputs are not clamped: whatever is typed is validated on "Get Rate".
# Out-of-range values show "Not available" instead of a premium.
# ============================================
st.subheader("🔢 Individual Premium Calculator")

col3, col4 = st.columns(2)
with col3:
    age = st.number_input(
        "Enter Age", value=None, step=1, placeholder=f"{AGE_MIN} – {AGE_MAX}",
        help=f"Age {AGE_MIN} – {AGE_MAX}.",
        key=f"age_manual_{loan_type}"
    )
with col4:
    tenure = st.number_input(
        "Enter Tenure (Years)", value=None, step=1,
        placeholder=f"{min_tenure} – {max_tenure}",
        help=f"Tenure in years ({min_tenure} – {max_tenure}).",
        key=f"tenure_manual_{loan_type}"
    )

sum_assured_manual = st.number_input(
    "Select Sum Assured (₹)", value=None, step=1,
    placeholder=f"{sa_min:,} – {sa_max:,}",
    help=f"Enter the exact Sum Assured for this member (₹{sa_min:,} – ₹{sa_max:,}).",
    key=f"sa_manual_{loan_type}"
)

NA = "—"  # shown in the premium boxes when the inputs are outside the allowed limits

if st.button("Get Rate", type="primary"):
    if age is None or tenure is None or sum_assured_manual is None:
        st.warning("Please enter Age, Tenure and Sum Assured.")
    else:
        problems = []
        if age < AGE_MIN or age > AGE_MAX:
            problems.append(f"Age must be between {AGE_MIN} and {AGE_MAX}")
        if tenure < min_tenure or tenure > max_tenure:
            problems.append(f"Tenure must be between {min_tenure} and {max_tenure} yrs")
        if sum_assured_manual < sa_min or sum_assured_manual > sa_max:
            problems.append(f"Sum Assured must be between ₹{sa_min:,} and ₹{sa_max:,}")

        if problems:
            st.warning("⚠️ " + " · ".join(problems))
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Premium (Excl. GST)", NA)
            with m2:
                st.metric(f"GST Amount ({GST_RATE_FIXED:.0f}%)", NA)
            with m3:
                st.metric("Premium (Incl. GST)", NA)
        else:
            try:
                df_rates, tenure_map = load_rate_table(loan_type)
                base_rate = get_rate(df_rates, tenure_map, int(age), int(tenure))
                premium_excl_gst, gst_amount, premium_incl_gst = compute_premium_breakdown(
                    base_rate, sum_assured_manual
                )
                st.success(
                    f"✅ {loan_type} | Age {int(age)} | Tenure {int(tenure)} yrs | "
                    f"Sum Assured ₹{int(sum_assured_manual):,} | GST {GST_RATE_FIXED:.0f}%"
                )
                m1, m2, m3 = st.columns(3)
                with m1:
                    st.metric("Premium (Excl. GST)", f"₹ {round(premium_excl_gst):,}")
                with m2:
                    st.metric(f"GST Amount ({GST_RATE_FIXED:.0f}%)", f"₹ {gst_amount:,.2f}")
                with m3:
                    st.metric("Premium (Incl. GST)", f"₹ {premium_incl_gst:,.2f}")
            except Exception as e:
                st.error(f"❌ Premium not available: {e}")

st.divider()

# ============================================
# GROUP PREMIUM CALCULATOR  (works on the Varth Capital template)
# Person downloads the template -> fills it -> uploads it here ->
# the same file comes back with Age, Rate, Premium, GST, Total and
# Tenure-in-months filled in. The template layout is left untouched.
# ============================================
TEMPLATE_FILE = "Premium_Template.xlsx"   # keep this file in the GitHub repo

head_col, dl_col = st.columns([3, 1])
with head_col:
    st.subheader("📂 Group Premium Calculator")
with dl_col:
    tpl_path = resolve_file(TEMPLATE_FILE)
    if tpl_path:
        with open(tpl_path, "rb") as f:
            st.download_button(
                "⬇ Download Template", data=f.read(),
                file_name="Varth_Capital_Premium_Template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    else:
        st.warning(f"'{TEMPLATE_FILE}' not found in the repo.")

with st.expander("ℹ️ How to use"):
    st.markdown(
        "1. Download the template, fill it in (columns marked **Mandatory**), and upload it below.\n"
        "2. **Loan Type** in each row decides the rate table: Vehicle Loan / LAP / Personal Loan. "
        "If it is left blank, the Loan Type selected at the top of the page is used.\n"
        "3. **Sum Assured** used = *Loan Outstanding Amount*; if that is blank, *Sum Assured* is used.\n"
        "4. **Age** is calculated from Date of Birth. **Tenure** is entered in years "
        "(*Cover Tenure In Years*) and the months columns are filled automatically.\n"
        "5. The same file comes back with Rate, Premium (Excl. GST), GST amount and Total Premium filled in. "
        "Rows that fail a check are left blank, with the reason in the last column."
    )
    st.markdown(
        "| Loan Type | Sum Assured | Tenure | Age |\n|---|---|---|---|\n" +
        "\n".join(
            f"| {k} | ₹{v['sa_min']:,} – ₹{v['sa_max']:,} | {v['t_min']} – {v['t_max']} yrs | {AGE_MIN} – {AGE_MAX} |"
            for k, v in SEGMENTS.items()
        )
    )


def norm_key(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def build_header_map(ws):
    m = {}
    for c in ws[1]:
        if c.value is not None and str(c.value).strip() != "":
            m.setdefault(norm_key(c.value), []).append(c.column)
    return m


def cols_for(hmap, key, prefix=False):
    out = []
    for k, v in hmap.items():
        if (k.startswith(key) if prefix else k == key):
            out.extend(v)
    return sorted(out)


def first_value(row_vals, cols):
    for c in cols:
        v = row_vals.get(c)
        if v is not None and str(v).strip() != "":
            return v
    return None


def to_num(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = v.replace(",", "").replace("₹", "").strip()
        if v == "":
            return None
    try:
        return float(v)
    except Exception:
        return None


def to_date(v):
    import datetime as dt
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):
        try:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))).date()
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    for f in ("%d%b%Y", "%d-%b-%Y", "%d %b %Y", "%d/%b/%Y", "%d/%m/%Y", "%d-%m-%Y",
              "%d.%m.%Y", "%d%m%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, f).date()
        except Exception:
            pass
    return None


def calc_age(dob, ref):
    # Age as on last birthday
    return ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))


def match_segment(v):
    if v is None:
        return None
    n = norm_key(v)
    if n in ("pl",) or "personal" in n:
        return "Personal Loan"
    if "lap" in n or "propert" in n:
        return "LAP"
    if "veh" in n or "vech" in n:
        return "Vehicle Loan"
    return None


def is_marker_row(vals):
    for v in vals:
        if isinstance(v, str) and norm_key(v).startswith(("mandatory", "nonmandatory", "optional")):
            return True
    return False


def clean_msg(e):
    return str(e).replace("\n", " ")


uploaded_file = st.file_uploader(
    "Upload the filled template", type=["xlsx"],
    help="Use the template downloaded above. Keep the column headings as they are."
)

if uploaded_file is not None:
    try:
        from openpyxl import load_workbook
        from copy import copy
        import datetime as dt

        raw = uploaded_file.getvalue()
        wb = load_workbook(io.BytesIO(raw))                    # keeps formatting; we write into this
        wb_v = load_workbook(io.BytesIO(raw), data_only=True)  # values to read
        ws, ws_v = wb.worksheets[0], wb_v.worksheets[0]
        hmap = build_header_map(ws)

        c_acct = cols_for(hmap, "loanaccountno", prefix=True)
        c_name = cols_for(hmap, "nameofprimaryloanborrower", prefix=True)
        c_type = cols_for(hmap, "loantype")
        c_dob = cols_for(hmap, "dateofbirth", prefix=True)
        c_os = cols_for(hmap, "loanoutstandingamount")
        c_sa = cols_for(hmap, "sumassured")
        c_disb = cols_for(hmap, "loandisbursementdate", prefix=True)
        c_eff = cols_for(hmap, "membereffectivedate")
        c_term_m = cols_for(hmap, "loanterminmonths")
        c_term_y = cols_for(hmap, "loantermyear")
        c_cov_m = cols_for(hmap, "covertenureinmonth", prefix=True)
        c_cov_y = cols_for(hmap, "covertenureinyears", prefix=True)
        c_age = cols_for(hmap, "mainmemberage")
        c_rate = cols_for(hmap, "rate")
        c_excl = cols_for(hmap, "premiumexclgst", prefix=True)
        c_gst = cols_for(hmap, "gstamount")
        c_incl = cols_for(hmap, "totalpremiuminclgst", prefix=True)

        needed = {
            "Loan Type": c_type, "Date of Birth": c_dob, "Sum Assured": c_sa,
            "Cover Tenure In Years": c_cov_y, "Premium (Excl. GST)": c_excl,
            "GST amount": c_gst, "Total Premium (incl GST)": c_incl,
        }
        missing = [k for k, v in needed.items() if not v]
        if missing:
            raise ValueError(
                "This does not look like the template — missing column(s): " + ", ".join(missing)
                + ". Please download the template again and use it as it is."
            )

        # "Remarks" column added at the far right (template columns are untouched)
        remarks_col = ws.max_column + 1
        src = ws.cell(row=1, column=ws.max_column)
        rc = ws.cell(row=1, column=remarks_col, value="Status / Remarks")
        rc.font, rc.fill, rc.border, rc.alignment = copy(src.font), copy(src.fill), copy(src.border), copy(src.alignment)
        ws.column_dimensions[rc.column_letter].width = 45

        def put(r, cols, value):
            if cols:
                ws.cell(row=r, column=cols[0], value=value)

        rate_cache = {}

        def rates_for(seg):
            if seg not in rate_cache:
                try:
                    rate_cache[seg] = load_rate_table(seg)
                except Exception as e:
                    rate_cache[seg] = e
            if isinstance(rate_cache[seg], Exception):
                raise rate_cache[seg]
            return rate_cache[seg]

        records = []
        for r in range(2, ws_v.max_row + 1):
            vals = {c: ws_v.cell(row=r, column=c).value for c in range(1, ws_v.max_column + 1)}
            if all(v is None or str(v).strip() == "" for v in vals.values()):
                continue
            if is_marker_row(vals.values()):
                continue

            seg = sa_used = age = ten_y = rate = lt_raw = None
            excl = gst = incl = None
            try:
                # ---- Loan type -> segment
                lt_raw = first_value(vals, c_type)
                if lt_raw is None:
                    seg = loan_type  # Loan Type blank in the row -> use the one selected at the top
                else:
                    seg = match_segment(lt_raw)
                    if seg is None:
                        raise ValueError(
                            f"Loan Type '{str(lt_raw).strip()}' not recognised - use Vehicle Loan, LAP or Personal Loan"
                        )
                cfg_r = SEGMENTS[seg]

                # ---- Tenure (years) -> months written back automatically
                ty = to_num(first_value(vals, c_cov_y))
                if ty is None:
                    tm = to_num(first_value(vals, c_cov_m))
                    if tm is not None:
                        ty = tm / 12.0
                if ty is None:
                    ty = to_num(first_value(vals, c_term_y))
                if ty is not None:
                    put(r, c_cov_y, round(ty, 2) if ty != round(ty) else int(round(ty)))
                    put(r, c_cov_m, int(round(ty * 12)))
                ly = to_num(first_value(vals, c_term_y))
                if ly is not None:
                    put(r, c_term_m, int(round(ly * 12)))

                # ---- Sum Assured: Loan Outstanding first, else Sum Assured
                os_v = to_num(first_value(vals, c_os))
                sa_v = to_num(first_value(vals, c_sa))
                sa_used = os_v if os_v is not None else sa_v
                if sa_used is None:
                    raise ValueError("Loan Outstanding / Sum Assured missing")

                # ---- Age from Date of Birth (as on Member Effective / Disbursement date, else today)
                dob_raw = first_value(vals, c_dob)
                dob = to_date(dob_raw)
                if dob is not None:
                    ref = to_date(first_value(vals, c_eff)) or to_date(first_value(vals, c_disb)) or dt.date.today()
                    age = calc_age(dob, ref)
                else:
                    age = to_num(first_value(vals, c_age))
                    if age is None:
                        raise ValueError("Date of Birth missing or not readable")
                    age = int(age)
                put(r, c_age, age)

                # ---- Limit checks
                if ty is None:
                    raise ValueError("Cover Tenure missing")
                if abs(ty - round(ty)) > 1e-9:
                    raise ValueError("Tenure must be in whole years")
                ten_y = int(round(ty))
                if age < AGE_MIN or age > AGE_MAX:
                    raise ValueError(f"Age {age} outside {AGE_MIN}–{AGE_MAX}")
                if ten_y < cfg_r["t_min"] or ten_y > cfg_r["t_max"]:
                    raise ValueError(f"Tenure {ten_y} yrs outside {cfg_r['t_min']}–{cfg_r['t_max']} yrs for {seg}")
                if sa_used < cfg_r["sa_min"] or sa_used > cfg_r["sa_max"]:
                    raise ValueError(f"Amount ₹{sa_used:,.0f} outside ₹{cfg_r['sa_min']:,}–₹{cfg_r['sa_max']:,} for {seg}")

                # ---- Rate + premium
                df_r, t_map = rates_for(seg)
                rate = get_rate(df_r, t_map, age, ten_y)
                excl, gst, incl = compute_premium_breakdown(rate, sa_used)
                put(r, c_rate, rate)
                put(r, c_excl, excl)
                put(r, c_gst, gst)
                put(r, c_incl, incl)
                status = "OK"
            except Exception as e:
                status = clean_msg(e)
                for cols in (c_rate, c_excl, c_gst, c_incl):
                    put(r, cols, None)
                excl = gst = incl = None

            ws.cell(row=r, column=remarks_col, value=status)
            acct = first_value(vals, c_acct)
            name = first_value(vals, c_name)
            records.append({
                "Row": r,
                "Loan Account No.": acct,
                "Borrower": name,
                "Loan Type": seg or lt_raw,
                "Age": age,
                "Tenure (yrs)": ten_y,
                "Amount Used (₹)": sa_used,
                "Rate": rate,
                "Premium (Excl. GST)": excl,
                "GST": gst,
                "Premium (Incl. GST)": incl,
                "Status": "✅" if status == "OK" else f"❌ {status}",
            })

        if not records:
            st.warning("No data rows found in the uploaded file.")
        else:
            res = pd.DataFrame(records)
            ok = res["Status"] == "✅"
            t_excl = pd.to_numeric(res["Premium (Excl. GST)"], errors="coerce").sum()
            t_gst = pd.to_numeric(res["GST"], errors="coerce").sum()
            t_incl = pd.to_numeric(res["Premium (Incl. GST)"], errors="coerce").sum()

            st.caption(f"{int(ok.sum())} row(s) calculated · {int((~ok).sum())} row(s) with errors")
            t1, t2, t3 = st.columns(3)
            with t1:
                st.metric("💰 Total Premium (Excl. GST)", f"₹ {round(t_excl):,}")
            with t2:
                st.metric(f"💰 Total GST ({GST_RATE_FIXED:.0f}%)", f"₹ {t_gst:,.2f}")
            with t3:
                st.metric("💰 Grand Total (Incl. GST)", f"₹ {t_incl:,.2f}")

            st.subheader("Result")
            st.dataframe(res, use_container_width=True, hide_index=True)

            buf = io.BytesIO()
            wb.save(buf)
            st.download_button(
                label="⬇ Download Filled Excel",
                data=buf.getvalue(),
                file_name="Varth_Capital_Premium_Output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    except Exception as e:
        st.error(f"Error: {e}")

st.divider()
st.caption("Powered by Policygrace")
