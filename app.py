from flask import Flask, redirect, render_template, request, session, g, jsonify
import sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
import os
import time
from datetime import date, datetime, timedelta
from calendar import monthrange
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")

#create function to get new db during each request
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db_path = os.path.join(BASE_DIR, "meals.db")
        db = g._database = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
    return db

#close db after request
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

#easier way to query. submit one as true if expecting only one row
def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.execute(query, args)
    if query.strip().lower().startswith("select"):
        rv = cur.fetchall()
    else:
        db.commit()
        rv = None
    cur.close()
    return (rv[0] if rv else None) if one else rv

def send_email(teacher_email, volunteer_email, teacher_name, meal_name, volunteer_name, dropoff_date):
    msg = EmailMessage()
    msg["Subject"] = f"Meals of Gratitude {datetime.today().strftime('%B %Y')}"
    msg["From"] = EMAIL
    msg["To"] = teacher_email
    msg["Cc"] = volunteer_email
    date = datetime.strptime(dropoff_date, "%Y-%m-%d")
    formatted_date = date.strftime("%A, %B ") + str(date.day)
    email_body_text = (
        f"Dear {teacher_name},\n\nThis email comes from the Meals of Gratitude program letting you "
        f"know that your meal, {meal_name}, will be delivered on the afternoon of {formatted_date} "
        f"by {volunteer_name} at the front office.\n\nPlease note that the parent volunteer has selected "
        f"this date and it may not be changed. Please let the volunteer (copied on this email) "
        f"know if you will be out of school on this date.\n\nIf you like the meal or would like to "
        f"provide feedback to make this program better, our volunteers would love to hear from you!\n\n"
        f"Sincerely,\n\nKovid Cerejo\n\nMeals of Gratitude Coordinator"
    )
    email_body_html = f"""
    <html>
        <body>
            <p>Dear {teacher_name},</p>
            <p>This email comes from the Meals of Gratitude program letting you know that your meal, <b>{meal_name}</b>, will be delivered on the afternoon of <b>{formatted_date}</b> by <b>{volunteer_name}</b> at the front office.</p>
            <p>Please note that the parent volunteer has selected this date and it may not be changed. Please let the volunteer (copied on this email) know if you will be out of school on this date.</p>
            <p>If you like the meal or would like to provide feedback to make this program better, our volunteers would love to hear from you!</p>
            <p>Sincerely,<br>
            Kovid Cerejo<br>
            Meals of Gratitude Coordinator</p>
        </body>
    </html>
    """
    msg.set_content(email_body_text)
    msg.add_alternative(email_body_html, subtype="html")

    recipients = [msg["To"], msg["Cc"]]

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL, APP_PASSWORD)
        smtp.send_message(msg, to_addrs=recipients)

@app.before_request
def login_required():
    if request.path.startswith("/admin") and request.path != "/admin/login":
        if not session.get("logged_in"):
            return redirect("/admin/login")

@app.before_request
def volunteer_code_required():
    if request.path.startswith("/volunteers") and request.path != "/volunteers/enter-code":
        current_version = query_db("SELECT id FROM volunteer_codes ORDER BY id DESC LIMIT 1", one=True)["id"]
        if not session.get("volunteer_verified") or session.get("volunteer_code_version") != current_version:
            return redirect("/volunteers/enter-code")

@app.before_request
def teacher_code_required():
    if request.path.startswith("/teachers") and request.path != "/teachers/enter-code":
        current_version = query_db("SELECT id FROM teacher_codes ORDER BY id DESC LIMIT 1", one=True)["id"]
        if not session.get("teacher_verified") or session.get("teacher_code_version") != current_version:
            return redirect("/teachers/enter-code")

@app.route("/volunteers/")
def volunteers():
    dates_const = query_db("SELECT month_year, volunteer_start, volunteer_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)
    date = dict(dates_const)
    date["volunteer_start"] = datetime.strptime(date["volunteer_start"], "%Y-%m-%d").date()
    date["volunteer_end"] = datetime.strptime(date["volunteer_end"], "%Y-%m-%d").date()
    today = datetime.today().date()
    return render_template("volunteers.html", date=date, today=today)

@app.route("/volunteers/enter-code", methods=["GET", "POST"])
def enter_volunteer_code():
    if request.method == "POST":
        entered_code = request.form.get("code")
        valid_code = query_db("SELECT id, code FROM volunteer_codes ORDER BY id DESC LIMIT 1", one=True)
        if entered_code != valid_code["code"]:
            return render_template("invalid_volunteer_code.html")
        else:
            session["volunteer_verified"] = True
            session["volunteer_code_version"] = valid_code["id"]
        return redirect("/volunteers")
    else:
        return render_template("volunteer_code.html")

@app.route("/volunteers/signups/")
def volunteer_signups():
    beg_month = datetime.today().strftime("%Y-%m")
    beg_month = beg_month + "-01"
    meals_const = query_db("""SELECT meals.id AS meal_id, recipes.name AS meal_name, date, volunteers.name 
                           AS volunteer_name FROM meals JOIN volunteers ON meals.volunteer_id = volunteers.id 
                           JOIN recipes ON meals.recipe_id = recipes.id WHERE date >= ? ORDER BY volunteer_name, date""", 
                           (beg_month,))
    gcs_const = query_db("""SELECT gift_cards.id AS gc_id, gift_cards.name AS gc_name, date, volunteers.name AS volunteer_name 
                         FROM gift_cards JOIN volunteers ON gift_cards.volunteer_id = volunteers.id WHERE date >= ?
                         ORDER BY volunteer_name, date""", (beg_month,))
    meals = []
    gcs = []
    for row in meals_const:
        meal = dict(row)
        meal["date"] = datetime.strptime(meal["date"], "%Y-%m-%d").date()
        meals.append(meal)
    for row in gcs_const:
        gc = dict(row)
        gc["date"] = datetime.strptime(gc["date"], "%Y-%m-%d").date()
        gcs.append(gc)
    dates_const = query_db("SELECT month_year, volunteer_start, volunteer_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)
    date = dict(dates_const)
    date["volunteer_start"] = datetime.strptime(date["volunteer_start"], "%Y-%m-%d").date()
    date["volunteer_end"] = datetime.strptime(date["volunteer_end"], "%Y-%m-%d").date()
    date["month_year"] = datetime.strptime(date["month_year"], "%B %Y").date()
    today = datetime.today().date()
    return render_template("volunteer_signups.html", meals=meals, gcs=gcs, date=date, today=today)

@app.route("/volunteers/signups/all-time")
def volunteer_signups_all():
    today = datetime.today().date()
    if today.month >= 8:
        year = today.year
    else:
        year = today.year - 1
    first = f"{year}-08-01"
    meals_const = query_db("""SELECT meals.id AS meal_id, recipes.name AS meal_name, date, volunteers.name 
                           AS volunteer_name FROM meals JOIN volunteers ON meals.volunteer_id = volunteers.id 
                           JOIN recipes ON meals.recipe_id = recipes.id WHERE date >= ? ORDER BY volunteer_name, date""", 
                           (first,))
    gcs_const = query_db("""SELECT gift_cards.id AS gc_id, gift_cards.name AS gc_name, date, volunteers.name AS volunteer_name 
                         FROM gift_cards JOIN volunteers ON gift_cards.volunteer_id = volunteers.id WHERE date >= ?
                         ORDER BY volunteer_name, date""", (first,))
    meals = []
    gcs = []
    for row in meals_const:
        meal = dict(row)
        meal["date"] = datetime.strptime(meal["date"], "%Y-%m-%d").date()
        meals.append(meal)
    for row in gcs_const:
        gc = dict(row)
        gc["date"] = datetime.strptime(gc["date"], "%Y-%m-%d").date()
        gcs.append(gc)
    return render_template("volunteer_signups_all.html", meals=meals, gcs=gcs)

@app.route("/volunteers/signups/edit-meal-<int:mealid>", methods=["GET", "POST"])
def edit_meal(mealid):
    if request.method == "POST":
        id = request.form.get("id")
        action = request.form.get("action")
        if action == "delete":
            query_db("DELETE FROM meals WHERE id = ?", (id,))
        else:
            date = request.form.get("date")
            recipe_id = request.form.get("recipe_id")
            query_db("UPDATE meals SET date = ?, recipe_id = ? WHERE id = ?", (date, recipe_id, id))
        return redirect("/volunteers/signups")
    else:
        meal_const = query_db("""SELECT meals.id AS meal_id, meals.date AS date, 
                            volunteers.name AS volunteer_name, recipes.name AS recipe_name,
                            recipes.id AS recipe_id FROM meals JOIN recipes ON meals.recipe_id = recipes.id
                            JOIN volunteers ON meals.volunteer_id = volunteers.id WHERE meals.id = ?""", 
                            (mealid,), one=True)
        
        if not meal_const:
            return redirect("/volunteers/signups")
        else:
            meal = dict(meal_const)
            meal["date"] = datetime.strptime(meal["date"], "%Y-%m-%d").date()
            dates_const = query_db("SELECT month_year, volunteer_start, volunteer_end FROM deadlines ORDER BY id DESC LIMIT 1", 
                                   one=True)
            date = dict(dates_const)
            date["volunteer_start"] = datetime.strptime(date["volunteer_start"], "%Y-%m-%d").date()
            date["volunteer_end"] = datetime.strptime(date["volunteer_end"], "%Y-%m-%d").date()
            date["month_year"] = datetime.strptime(date["month_year"], "%B %Y").date()
            today = datetime.today().date()
            recipes = query_db("SELECT name, id FROM recipes")
            start = query_db("SELECT dropoff_start FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_start"]
            end = query_db("SELECT dropoff_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_end"]
            return render_template("edit_meal.html", meal=meal, recipes=recipes, start=start, end=end, date=date, today=today)

@app.route("/volunteers/signups/edit-gc-<int:gcid>", methods=["GET", "POST"])
def edit_gc(gcid):  
    if request.method == "POST":
        id = request.form.get("id")
        action = request.form.get("action")
        if action == "delete":
            query_db("DELETE FROM gift_cards WHERE id = ?", (id,))
        else:
            date = request.form.get("date")
            gc_name = request.form.get("gc_name")
            query_db("UPDATE gift_cards SET name = ?, date = ? WHERE id = ?", (gc_name, date, id))
        return redirect("/volunteers/signups")
    else:
        gc_const = query_db("""SELECT gift_cards.id AS gc_id, gift_cards.name AS gc_name, 
                      gift_cards.date AS date, volunteers.name AS volunteer_name 
                      FROM gift_cards JOIN volunteers ON gift_cards.volunteer_id = 
                      volunteers.id WHERE gift_cards.id = ?""", (gcid,), one=True)
        if not gc_const:
            return redirect("/volunteers/signups")
        gc = dict(gc_const)
        gc["date"] = datetime.strptime(gc["date"], "%Y-%m-%d").date()
        dates_const = query_db("SELECT month_year, volunteer_start, volunteer_end FROM deadlines ORDER BY id DESC LIMIT 1", 
                               one=True)
        date = dict(dates_const)
        date["volunteer_start"] = datetime.strptime(date["volunteer_start"], "%Y-%m-%d").date()
        date["volunteer_end"] = datetime.strptime(date["volunteer_end"], "%Y-%m-%d").date()
        date["month_year"] = datetime.strptime(date["month_year"], "%B %Y").date()
        today = datetime.today().date()
        start = query_db("SELECT dropoff_start FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_start"]
        end = query_db("SELECT dropoff_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_end"]
        return render_template("edit_gc.html", gc=gc, start=start, end=end, today=today, date=date)

@app.route("/volunteers/gc-signup", methods=["GET", "POST"])
def gc_signup():
    if request.method == "POST":
        volunteer_name = request.form.get("name")
        gc_name = request.form.get("gc_name")
        date = request.form.get("date")
        volunteer_id = query_db("SELECT id FROM volunteers WHERE name = ?", (volunteer_name,), one=True)["id"]
        query_db("INSERT INTO gift_cards (name, date, volunteer_id) VALUES (?, ?, ?)", (gc_name, date, volunteer_id))
        return redirect("/volunteers/signups")
    else:
        dates_const = query_db("SELECT month_year, volunteer_start, volunteer_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)
        date = dict(dates_const)
        date["volunteer_start"] = datetime.strptime(date["volunteer_start"], "%Y-%m-%d").date()
        date["volunteer_end"] = datetime.strptime(date["volunteer_end"], "%Y-%m-%d").date()
        today = datetime.today().date()
        volunteers = query_db("SELECT name FROM volunteers")
        start = query_db("SELECT dropoff_start FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_start"]
        end = query_db("SELECT dropoff_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_end"]
        return render_template("gc_signup.html", volunteers=volunteers, start=start, end=end, today=today, date=date)

@app.route("/volunteers/meal-signup", methods=["GET", "POST"])
def meal_signup():
    if request.method == "POST":
        volunteer_name = request.form.get("name")
        meal_name = request.form.get("meal")
        recipe_id = query_db("SELECT id FROM recipes WHERE name = ?", (meal_name,), one=True)["id"]
        date = request.form.get("date")
        volunteer_id = query_db("SELECT id FROM volunteers WHERE name = ?",
                                (volunteer_name,), one=True)["id"]
        query_db("INSERT INTO meals (recipe_id, date, volunteer_id) VALUES (?, ?, ?)",
                  (recipe_id, date, volunteer_id))
        return redirect("/volunteers/signups")
    else:
        dates_const = query_db("SELECT month_year, volunteer_start, volunteer_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)
        date = dict(dates_const)
        date["volunteer_start"] = datetime.strptime(date["volunteer_start"], "%Y-%m-%d").date()
        date["volunteer_end"] = datetime.strptime(date["volunteer_end"], "%Y-%m-%d").date()
        today = datetime.today().date()
        volunteers = query_db("SELECT name FROM volunteers")
        recipes = query_db("SELECT name FROM recipes")
        start = query_db("SELECT dropoff_start FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_start"]
        end = query_db("SELECT dropoff_end FROM deadlines ORDER BY id DESC LIMIT 1", one=True)["dropoff_end"]
        return render_template("meal_signup.html", volunteers=volunteers, recipes=recipes, start=start, end=end, today=today, date=date)

@app.route("/teachers/")
def teachers():
    today_1 = datetime.today().date()
    month_year = today_1.strftime("%B %Y")
    dates_const = query_db("SELECT month_year, teacher_start, teacher_end FROM deadlines WHERE month_year = ?", (month_year,), one=True)
    dates = dict(dates_const)
    if dates["teacher_start"]:
        dates["teacher_start"] = datetime.strptime(dates["teacher_start"], "%Y-%m-%d").date()
    dates["teacher_end"] = datetime.strptime(dates["teacher_end"], "%Y-%m-%d").date()
    today = datetime.today().date()
    return render_template("teachers.html", dates=dates, today=today)

@app.route("/teachers/enter-code", methods=["GET", "POST"])
def enter_teacher_code():
    if request.method == "POST":
        entered_code = request.form.get("code")
        valid_code = query_db("SELECT id, code FROM teacher_codes ORDER BY id DESC LIMIT 1", one=True)
        if entered_code != valid_code["code"]:
            return render_template("invalid_teacher_code.html")
        else:
            session["teacher_verified"] = True
            session["teacher_code_version"] = valid_code["id"]
        return redirect("/teachers")
    else:
        return render_template("teacher_code.html")

@app.route("/teachers/reward-signup", methods=["GET", "POST"])
def teachers_reward_signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        id = request.form.get("id")
        reward_type = request.form.get("reward_type")
        if not (name and email and id and reward_type):
            return redirect("/teachers/reward-signup")
        if reward_type not in ["meals", "gift_cards"]:
            return redirect("/teachers/reward-signup")
        query_db("INSERT OR IGNORE INTO teachers (name, email) VALUES (?, ?)", (name, email))
        query_db(f"UPDATE {reward_type} SET teacher_id = (SELECT id FROM teachers WHERE name = ? AND email = ?) WHERE id = ?",
                 (name, email, id))
        return redirect("/teachers/reward-signup")
    else:
        today_1 = datetime.today().date()
        month_year = today_1.strftime("%B %Y")
        dates_const = query_db("SELECT month_year, teacher_start, teacher_end FROM deadlines WHERE month_year = ?", (month_year,), one=True)
        dates = dict(dates_const)
        if dates["teacher_start"]:
            dates["teacher_start"] = datetime.strptime(dates["teacher_start"], "%Y-%m-%d").date()
        dates["teacher_end"] = datetime.strptime(dates["teacher_end"], "%Y-%m-%d").date()
        today = datetime.today().date()
        beg_month = datetime.today().strftime("%Y-%m")
        start_date = beg_month + "-01"
        end_date = beg_month + f"-{str(monthrange(today.year, today.month)[1])}"
        meals_const = query_db("""SELECT meals.id AS meal_id, recipes.name AS meal_name, date, teachers.name AS teacher_name, 
                               recipes.id AS recipe_id FROM meals JOIN recipes ON meals.recipe_id = recipes.id LEFT JOIN 
                               teachers ON meals.teacher_id = teachers.id WHERE date >= ? AND date <= ? ORDER BY meal_name""",
                                (start_date, end_date))
        meals = []
        for row in meals_const:
            meal = dict(row)
            meal["date"] = datetime.strptime(meal["date"], "%Y-%m-%d").date()
            meals.append(meal)
        gcs_const = query_db("""SELECT gift_cards.id AS gc_id, gift_cards.name AS gc_name, date, teachers.name AS teacher_name
                             FROM gift_cards LEFT JOIN teachers ON gift_cards.teacher_id = teachers.id WHERE date >= ? AND date <= ?
                             ORDER BY gift_cards.name""", (start_date, end_date))
        gcs = []
        for row in gcs_const:
            gc = dict(row)
            gc["date"] = datetime.strptime(gc["date"], "%Y-%m-%d").date()
            gcs.append(gc)
        return render_template("teacher_rewards.html", meals=meals, gcs=gcs, dates=dates, today=today)

@app.route("/recipes/")
def recipes():
    recipes = query_db("""SELECT recipes.id, recipes.name AS recipe_name, volunteers.name 
                       AS volunteer_name FROM recipes JOIN volunteers 
                       ON recipes.creator_id = volunteers.id ORDER BY recipe_name""")
    return render_template("recipes.html", recipes=recipes)

@app.route("/recipes/upload", methods=["GET", "POST"])
def upload_recipe():
    if request.method == "POST":
        recipe_name = request.form.get("recipe_name")
        ingredients = request.form.get("ingredients")
        instructions = request.form.get("instructions")
        creator = request.form.get("creator_name")
        if not (recipe_name and ingredients and instructions and creator):
            return redirect("/recipes")
        creator_id = query_db("SELECT id FROM volunteers WHERE name = ?", (creator,), one=True)["id"]
        image = request.files.get("image")
        if image and image.filename != "":
            filename = secure_filename(image.filename)
            filename = f"{int(time.time())}_{filename}"
            save_path = os.path.join("static", "images", "recipes", filename)
            image.save(save_path)
            image_url = f"images/recipes/{filename}"
        else:
            image_url = None
        query_db("""INSERT INTO recipes (name, ingredients, instructions, creator_id, image_url)
                 VALUES (?, ?, ?, ?, ?)""", (recipe_name, ingredients, instructions, creator_id, image_url))
        return redirect("/recipes/")
    else:
        volunteers = query_db("SELECT name FROM volunteers")
        return render_template("upload_recipe.html", volunteers=volunteers)

@app.route("/recipes/<int:id>")
def recipe(id):
    recipe = query_db("""SELECT recipes.name AS recipe_name, ingredients, instructions, 
                      image_url, volunteers.name AS volunteer_name FROM recipes JOIN volunteers 
                      ON recipes.creator_id = volunteers.id WHERE recipes.id = ?""", 
                      (id,), one=True)
    if not recipe:
        return redirect("/recipes/")
    return render_template("recipe.html", recipe=recipe)

@app.route("/admin/",)
def admin():
    return render_template("admin.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("pw")
        if not pw:
            return redirect("/admin/login")
        hash = query_db("SELECT hash FROM passwords WHERE username = 'admin'", one=True)["hash"]
        if check_password_hash(hash, pw):
            session["logged_in"] = True
            return redirect("/admin")
        else:
            return render_template("wrong_pw.html")
    else:
        return render_template("admin_login.html")

@app.route("/admin/volunteers/", methods=["GET", "POST"])
def admin_volunteers():
    if request.method == "POST":
        return redirect("/admin/volunteers")
    else:
        volunteers_const = query_db("SELECT * FROM volunteers ORDER BY name")
        volunteers = []
        for row in volunteers_const:
            volunteer = dict(row)
            volunteer["date_added"] = datetime.strptime(volunteer["date_added"], "%Y-%m-%d").date()
            volunteers.append(volunteer)
        return render_template("admin_volunteers.html", volunteers=volunteers)
    
@app.route("/admin/volunteers/add", methods=["GET", "POST"])
def add_volunteer():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        if not (name and email and phone):
            return redirect("/admin/volunteers/")
        today = datetime.today().date()
        query_db("INSERT INTO volunteers (name, email, phone, date_added) VALUES (?, ?, ?, ?)", (name, email, phone, today.isoformat()))
        return redirect("/admin/volunteers/")
    else:
        return render_template("add_volunteer.html")
    
@app.route("/admin/volunteers/delete", methods=["POST"])
def delete_volunteer():
    data = request.get_json()
    id = data.get('id')
    query_db("DELETE FROM volunteers WHERE id = ?", (id,))
    return jsonify(success=True)

@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect("/admin/login")

@app.route("/admin/set-volunteer-code", methods=["GET", "POST"])
def set_volunteer_code():
    if request.method == "POST":
        new_code = request.form.get("code")
        if not new_code:
            return redirect("/admin")
        query_db("INSERT INTO volunteer_codes (code) VALUES (?)", (new_code,))
        return redirect("/admin")
    else:
        current_code = query_db("SELECT code FROM volunteer_codes ORDER BY id DESC LIMIT 1", one=True)["code"]
        return render_template("set_volunteer_code.html", current_code=current_code)

@app.route("/admin/set-teacher-code", methods=["GET", "POST"])
def set_teacher_code():
    if request.method == "POST":
        new_code = request.form.get("code")
        if not new_code:
            return redirect("/admin")
        query_db("INSERT INTO teacher_codes (code) VALUES (?)", (new_code,))
        return redirect("/admin")
    else:
        current_code = query_db("SELECT code FROM teacher_codes ORDER BY id DESC LIMIT 1", one=True)["code"]
        return render_template("set_teacher_code.html", current_code=current_code)


@app.route("/admin/push-to-teachers", methods=["POST"])
def push_teachers():
    date = datetime.today().strftime("%Y-%m-%d")
    query_db("UPDATE deadlines SET teacher_start = ? WHERE id = (SELECT MAX(id) FROM deadlines)", (date,))
    return redirect("/admin")

@app.route("/admin/override-signups")
def override_signup():
    beg_month = datetime.today().strftime("%Y-%m")
    beg_month = beg_month + "-01"
    meals_const = query_db("""SELECT meals.id AS meal_id, recipes.name AS meal_name, date, volunteers.name 
                        AS volunteer_name FROM meals JOIN volunteers ON meals.volunteer_id = volunteers.id 
                        JOIN recipes ON meals.recipe_id = recipes.id WHERE date >= ? ORDER BY volunteer_name, date""", 
                        (beg_month,))
    gcs_const = query_db("""SELECT gift_cards.id AS gc_id, gift_cards.name AS gc_name, date, volunteers.name AS volunteer_name 
                        FROM gift_cards JOIN volunteers ON gift_cards.volunteer_id = volunteers.id WHERE date >= ?
                        ORDER BY volunteer_name, date""", (beg_month,))
    meals = []
    gcs = []
    for row in meals_const:
        meal = dict(row)
        meal["date"] = datetime.strptime(meal["date"], "%Y-%m-%d").date()
        meals.append(meal)
    for row in gcs_const:
        gc = dict(row)
        gc["date"] = datetime.strptime(gc["date"], "%Y-%m-%d").date()
        gcs.append(gc)
    return render_template("override_signups.html", meals=meals, gcs=gcs)

@app.route("/admin/edit-meal-<int:mealid>", methods=["GET", "POST"])
def admin_edit_meal(mealid):
    if request.method == "POST":
        id = request.form.get("id")
        action = request.form.get("action")
        if action == "delete":
            query_db("DELETE FROM meals WHERE id = ?", (id,))
        elif action == "edit":
            date = request.form.get("date")
            recipe_id = request.form.get("recipe_id")
            query_db("UPDATE meals SET date = ?, recipe_id = ? WHERE id = ?", (date, recipe_id, id))
        return redirect("/admin/override-signups")
    else:
        meal_const = query_db("""SELECT meals.id AS meal_id, meals.date AS date, 
                            volunteers.name AS volunteer_name, recipes.name AS recipe_name,
                            recipes.id AS recipe_id FROM meals JOIN recipes ON meals.recipe_id = recipes.id
                            JOIN volunteers ON meals.volunteer_id = volunteers.id WHERE meals.id = ?""", 
                            (mealid,), one=True)
        
        if not meal_const:
            return redirect("/admin/override-signups")
        else:
            meal = dict(meal_const)
            meal["date"] = datetime.strptime(meal["date"], "%Y-%m-%d").date()
            recipes = query_db("SELECT name, id FROM recipes")
            return render_template("admin_edit_meal.html", meal=meal, recipes=recipes)

@app.route("/admin/edit-gc-<int:gcid>", methods=["GET", "POST"])
def admin_edit_gc(gcid):
    if request.method == "POST":
        id = request.form.get("id")
        action = request.form.get("action")
        if action == "delete":
            query_db("DELETE FROM gift_cards WHERE id = ?", (id,))
        elif action == "edit":
            date = request.form.get("date")
            gc_name = request.form.get("gc_name")
            query_db("UPDATE gift_cards SET name = ?, date = ? WHERE id = ?", (gc_name, date, id))
        return redirect("/admin/override-signups")
    else:
        gc_const = query_db("""SELECT gift_cards.id AS gc_id, gift_cards.name AS gc_name, 
                      gift_cards.date AS date, volunteers.name AS volunteer_name 
                      FROM gift_cards JOIN volunteers ON gift_cards.volunteer_id = 
                      volunteers.id WHERE gift_cards.id = ?""", (gcid,), one=True)
        if not gc_const:
            return redirect("/admin/override-signups")
        gc = dict(gc_const)
        gc["date"] = datetime.strptime(gc["date"], "%Y-%m-%d").date()
        return render_template("admin_edit_gc.html", gc=gc)
    
@app.route("/admin/add-meal", methods=["GET", "POST"])
def admin_add_meal():
    if request.method == "POST":
        volunteer_name = request.form.get("name")
        meal_name = request.form.get("meal")
        recipe_id = query_db("SELECT id FROM recipes WHERE name = ?", (meal_name,), one=True)["id"]
        date = request.form.get("date")
        volunteer_id = query_db("SELECT id FROM volunteers WHERE name = ?",
                                (volunteer_name,), one=True)["id"]
        query_db("INSERT INTO meals (recipe_id, date, volunteer_id) VALUES (?, ?, ?)",
                  (recipe_id, date, volunteer_id))
        return redirect("/admin/override-signups")
    else:
        volunteers = query_db("SELECT name FROM volunteers")
        recipes = query_db("SELECT name FROM recipes")
        return render_template("admin_add_meal.html", volunteers=volunteers, recipes=recipes)
    
@app.route("/admin/add-gc", methods=["GET", "POST"])
def admin_add_gc():
    if request.method == "POST":
        volunteer_name = request.form.get("name")
        gc_name = request.form.get("gc_name")
        date = request.form.get("date")
        volunteer_id = query_db("SELECT id FROM volunteers WHERE name = ?", (volunteer_name,), one=True)["id"]
        query_db("INSERT INTO gift_cards (name, date, volunteer_id) VALUES (?, ?, ?)", (gc_name, date, volunteer_id))
        return redirect("/admin/override-signups")
    else:
        volunteers = query_db("SELECT name FROM volunteers")
        return render_template("admin_add_gc.html", volunteers=volunteers)

@app.route("/admin/recipes")
def admin_recipes():
    recipes = query_db("""SELECT recipes.id, recipes.name AS recipe_name, volunteers.name 
                       AS volunteer_name FROM recipes JOIN volunteers 
                       ON recipes.creator_id = volunteers.id ORDER BY recipe_name""")
    return render_template("admin_recipes.html", recipes=recipes)

@app.route("/admin/edit-recipe-<int:recipeid>", methods=["GET", "POST"])
def admin_edit_recipe(recipeid):
    if request.method == "POST":
        action = request.form.get("action")
        if action == "edit":
            recipe_name = request.form.get("recipe_name")
            ingredients = request.form.get("ingredients")
            instructions = request.form.get("instructions")
            query_db("""UPDATE recipes SET name = ?, ingredients = ?, instructions = ? WHERE id = ?""",
                    (recipe_name, ingredients, instructions, recipeid))
            image = request.files.get("image")
            if image and image.filename:
                filename = secure_filename(image.filename)
                filename = f"{int(time.time())}_{filename}"
                save_path = os.path.join("static", "images", "recipes", filename)
                image.save(save_path)
                old_url = query_db("SELECT image_url FROM recipes WHERE id = ?", (recipeid,), one=True)["image_url"]
                if old_url:
                    old_path = os.path.join("static", old_url)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                image_url = f"images/recipes/{filename}"
                query_db("UPDATE recipes SET image_url = ? WHERE id = ?", 
                        (image_url, recipeid))
        else:
            old_url = query_db("SELECT image_url FROM recipes WHERE id = ?", (recipeid,), one=True)["image_url"]
            if old_url:
                old_path = os.path.join("static", old_url)
                if os.path.exists(old_path):
                    os.remove(old_path)
            query_db("DELETE FROM recipes WHERE id = ?", (recipeid,))
        return redirect("/admin/recipes")
    else:
        recipe = query_db("""SELECT id, name, ingredients, instructions, image_url FROM recipes
                          WHERE id = ?""", (recipeid,), one=True)
        if not recipe:
            return redirect("/admin/recipes")
        return render_template("admin_edit_recipe.html", recipe=recipe)
    
@app.route("/admin/deadlines/")
def deadlines():
    deadlines_const = query_db("SELECT * FROM deadlines ORDER BY id DESC")
    deadlines = []
    for row in deadlines_const:
        deadline = dict(row)
        deadline["volunteer_start"] = datetime.strptime(deadline["volunteer_start"], "%Y-%m-%d").date()
        deadline["volunteer_end"] = datetime.strptime(deadline["volunteer_end"], "%Y-%m-%d").date()
        deadline["dropoff_start"] = datetime.strptime(deadline["dropoff_start"], "%Y-%m-%d").date()
        deadline["dropoff_end"] = datetime.strptime(deadline["dropoff_end"], "%Y-%m-%d").date()
        if deadline["teacher_start"]:
            deadline["teacher_start"] = datetime.strptime(deadline["teacher_start"], "%Y-%m-%d").date()
        deadline["teacher_end"] = datetime.strptime(deadline["teacher_end"], "%Y-%m-%d").date()
        deadlines.append(deadline)
    return render_template("admin_deadlines.html", deadlines=deadlines)

@app.route("/admin/deadlines/set", methods=["GET", "POST"])
def set_volunteer_dates():
    if request.method == "POST":
        month = request.form.get("month")
        month_datetime = datetime.strptime(month + "-01", "%Y-%m-%d")
        month_year = month_datetime.strftime("%B %Y")
        range_start = request.form.get("range_start")
        range_end = request.form.get("range_end")
        teacher_end_temp = datetime.strptime(range_start, "%Y-%m-%d").date()
        teacher_end = teacher_end_temp - timedelta(days=3)
        deadline = request.form.get("deadline")
        query_db("""INSERT INTO deadlines (month_year, volunteer_end, dropoff_start, dropoff_end, teacher_end) 
                 VALUES (?, ?, ?, ?, ?)""", (month_year, deadline, range_start, range_end, teacher_end))
        return redirect("/admin/deadlines/")
    else:
        today = datetime.today()
        year = today.year
        month = today.month
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        next_month = f"{year}-{month:02d}"
        return render_template("set_volunteer_dates.html", next_month=next_month)

@app.route("/admin/deadlines/edit-<int:id>", methods=["GET", "POST"])
def edit_deadline(id):
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            query_db("DELETE FROM deadlines WHERE id = ?", (id,))
            return redirect("/admin/deadlines/")
        month = request.form.get("month")
        month_datetime = datetime.strptime(month + "-01", "%Y-%m-%d")
        month_year = month_datetime.strftime("%B %Y")
        range_start = request.form.get("range_start")
        range_end = request.form.get("range_end")
        deadline = request.form.get("deadline")
        query_db("""UPDATE deadlines SET month_year = ?, volunteer_end = ?, dropoff_start = ?, 
                 dropoff_end = ? WHERE id = ?""", (month_year, deadline, range_start, range_end, id))
        return redirect("/admin/deadlines/")
    else:
        deadline_const = query_db("SELECT * FROM deadlines WHERE id = ?", (id,), one=True)
        if not deadline_const:
            return redirect("/admin/deadlines/")
        deadline = dict(deadline_const)
        deadline["month_year"] = datetime.strptime(deadline["month_year"], "%B %Y").strftime("%Y-%m")
        return render_template("edit_deadline.html", deadline=deadline)
    
@app.route("/admin/rankings")
def admin_rankings():
    volunteers_const = query_db("SELECT id, name FROM volunteers")
    volunteers = []
    for row in volunteers_const:
        volunteer = dict(row)
        gc_count = query_db("SELECT COUNT(volunteer_id) AS count FROM gift_cards WHERE volunteer_id = ?", 
                            (volunteer["id"],), one=True)["count"]
        meal_count = query_db("SELECT COUNT(volunteer_id) AS count FROM meals WHERE volunteer_id = ?", 
                              (volunteer["id"],), one=True)["count"]
        volunteer["reward_count"] = gc_count + meal_count
        volunteers.append(volunteer)
    recipes_const = query_db("""SELECT recipes.id AS id, recipes.name AS recipe_name, volunteers.name AS volunteer_name 
                             FROM recipes JOIN volunteers ON recipes.creator_id = volunteers.id""")
    recipes = []
    for row in recipes_const:
        recipe = dict(row)
        recipe["count"] = query_db("SELECT COUNT(recipe_id) AS count FROM meals WHERE recipe_id = ?",
                                   (recipe["id"],), one=True)["count"]
        recipes.append(recipe)
    return render_template("rankings.html", volunteers=volunteers, recipes=recipes)

@app.route("/admin/send-emails")
def admin_send_emails():
    today = datetime.today().date()
    month_year = today.strftime("%B %Y")
    deadlines = query_db("SELECT dropoff_start, dropoff_end FROM deadlines WHERE month_year = ?", (month_year,), one=True)
    meals = query_db("""SELECT date AS dropoff_date, recipes.name AS meal_name, volunteers.name AS volunteer_name, 
                     volunteers.email AS volunteer_email, teachers.name AS teacher_name, teachers.email 
                     AS teacher_email FROM meals JOIN recipes ON recipes.id = meals.recipe_id 
                     JOIN volunteers ON volunteers.id = meals.volunteer_id JOIN teachers ON 
                     teachers.id = meals.teacher_id WHERE date >= ? AND date <= ?""", (deadlines["dropoff_start"], deadlines["dropoff_end"]))
    for meal in meals:
        send_email(teacher_email=meal["teacher_email"], volunteer_email=meal["volunteer_email"], 
               teacher_name=meal["teacher_name"], volunteer_name=meal["volunteer_name"], meal_name=meal["meal_name"], 
               dropoff_date=meal["dropoff_date"])
    return redirect("/admin")