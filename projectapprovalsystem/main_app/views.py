from pyexpat import model
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from datetime import date
from sentence_transformers import SentenceTransformer, util

# Load lightweight but powerful model
_sbert_model = None

def get_sbert_model():
    global _sbert_model
    if _sbert_model is None:
        _sbert_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _sbert_model


from .models import UserRegistration, Project, Projectsubmission, SubmissionDeadline
from .forms import (
    ProjectForm,
    ProjectSubmissionForm,
    SubmissionDeadlineForm,
    EditProfileForm
)
from rapidfuzz import fuzz



# -------------------- HOME PAGE --------------------
def home(request):
    if request.session.get('user_id'):
        return redirect('index')
    return render(request, 'base.html')


# -------------------- LOGIN --------------------
def login_page(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '').strip()
        role = request.POST.get('role', '').strip().lower()

        # 🧩 Validate form fields
        if not email or not password or not role:
            messages.error(request, "⚠️ Please fill in all required fields.")
            return redirect('login_page')

        # 🔍 Try to find user by email
        try:
            user = UserRegistration.objects.get(email=email)
        except UserRegistration.DoesNotExist:
            messages.error(request, "❌ No account found with this email. Please register first.")
            return redirect('login_page')

        # 🚫 Block deleted users
        if user.is_deleted:
            messages.error(request, "🚫 This account has been deactivated by the admin.")
            return redirect('login_page')

        # 🚫 Role mismatch (extra layer of security)
        if user.role != role:
            messages.error(request, f"⚠️ You are registered as a {user.role.title()}, not {role.title()}.")
            return redirect('login_page')

        # 🔐 Verify password
        if not user.check_password(password):
            messages.error(request, "❌ Incorrect password. Please try again.")
            return redirect('login_page')

        # ⏳ Check verification status
        if not user.is_verified:
            messages.warning(request, "⏳ Your account is awaiting admin approval.")
            return redirect('login_page')

        # ✅ All good — create session
        request.session['user_id'] = user.id
        request.session['role'] = user.role

        messages.success(request, f"👋 Welcome back, {user.full_name}!")

        # 🎯 Redirect by role
        if user.role == 'admin':
            return redirect('admin_dashboard')
        elif user.role == 'teacher':
            return redirect('teacher_dashboard')
        elif user.role == 'student':
            return redirect('student_dashboard')
        else:
            messages.error(request, "⚠️ Invalid user role detected.")
            return redirect('login_page')

    # Render login page for GET requests
    return render(request, 'login.html')


# -------------------- INDEX --------------------
def index(request):
    if not request.session.get('user_id'):
        messages.error(request, "You must login first!")
        return redirect('login_page')

    role = request.session.get('role', '').lower()
    if role == "student":
        return redirect('student_dashboard')
    elif role == "teacher":
        return redirect('teacher_dashboard')
    elif role == "admin":
        return redirect('admin_dashboard')

    messages.error(request, "Unknown role. Please contact admin.")
    return redirect('login_page')


# -------------------- STUDENT DASHBOARD --------------------


def student_dashboard(request):
    user_id = request.session.get('user_id')
    role = request.session.get('role')

    if not user_id or role != 'student':
        messages.error(request, "Unauthorized access.")
        return redirect('login_page')

    student = get_object_or_404(UserRegistration, id=user_id)

    # 🧑‍🏫 Check if assigned teacher deleted
    teacher_removed = False
    teacher_name = None
    if student.assigned_teacher and student.assigned_teacher.is_deleted:
        teacher_removed = True
        teacher_name = student.assigned_teacher.full_name

    # -------------------- DEADLINE CALCULATION --------------------
    latest_deadline = SubmissionDeadline.objects.order_by('-created_at').first()
    deadline_info = None
    deadline_passed = False

    if latest_deadline and latest_deadline.deadline:
        today = timezone.now().date()
        days_left = (latest_deadline.deadline - today).days

        if days_left > 1:
            deadline_info = {'text': f"🕒 {days_left} days left to submit your project.", 'color': '#2563eb'}
        elif days_left == 1:
            deadline_info = {'text': "⚠️ Tomorrow is the last day to submit!", 'color': '#f59e0b'}
        elif days_left == 0:
            deadline_info = {'text': "🚨 Today is the final submission day!", 'color': '#eab308'}
        else:
            deadline_info = {'text': "❌ Submission deadline has passed.", 'color': '#dc2626'}
            deadline_passed = True

    # -------------------------------------------------------------
    submitted_projects = Projectsubmission.objects.filter(student=student)
    existing_project = Projectsubmission.objects.filter(
        student=student,
        status__in=['Pending', 'Approved']
    ).first()

    form = ProjectSubmissionForm()

    # -------------------------------------------------------------
    # 🔥 BLOCK SUBMISSION IF TEACHER REMOVED
    # -------------------------------------------------------------
    if teacher_removed:
        messages.warning(request, f"⚠️ Your assigned guide {teacher_name} has been removed. You cannot submit.")
        return render(request, 'student_dashboard.html', {
            "student": student,
            "submitted_projects": submitted_projects,
            "deadline_info": deadline_info,
            "deadline_passed": deadline_passed,
            "teacher_removed": teacher_removed,
            "teacher_name": teacher_name,
            "duplicate_warning": request.session.get("duplicate_warning"),
        })

    # -------------------------------------------------------------
    # 🔥 BLOCK POST IF DEADLINE PASSED
    # -------------------------------------------------------------
    # GET → show blocked page
    if deadline_passed and request.method == "GET":
        return render(request, "submit_blocked.html", {
            "student": student,
            "message": "⏰ The project submission deadline has passed.",
            "color": "#ef4444",
        })

    # POST → block and redirect
    if deadline_passed and request.method == "POST":
        messages.error(request, "❌ Submission deadline has passed.")
        return redirect("student_dashboard")


    # -------------------------------------------------------------
    # 🔥 BLOCK POST IF EXISTING PENDING/APPROVED PROJECT EXISTS
    # -------------------------------------------------------------
    if request.method == "POST" and existing_project:
        messages.error(request, "⚠️ You already have a project under review.")
        return redirect("student_dashboard")

    # -------------------------------------------------------------
    # 📝 PROCESS NEW SUBMISSION (ONLY IF ALLOWED)
    # -------------------------------------------------------------
    if request.method == "POST":
        form = ProjectSubmissionForm(request.POST)

        if form.is_valid():
            title = form.cleaned_data['title']
            description = form.cleaned_data['description']
            technology = form.cleaned_data['technology_used']

            student_text = f"{title} {description} {technology}".lower()

            # ---- Semantic AI similarity ----
            model = get_sbert_model()
            student_emb = model.encode(student_text, convert_to_tensor=True)
            approved_projects = Projectsubmission.objects.filter(status='Approved')

            duplicate_found = False
            best_similarity = 0
            best_project = None

            for proj in approved_projects:
                existing_text = f"{proj.title} {proj.description} {proj.technology_used}".lower()
                model = get_sbert_model()
                existing_emb = model.encode(existing_text, convert_to_tensor=True)


                semantic_score = float(util.cos_sim(student_emb, existing_emb)[0][0]) * 100
                fuzz_score = fuzz.WRatio(student_text, existing_text)

                final_similarity = round((semantic_score * 0.6) + (fuzz_score * 0.4))

                if final_similarity > best_similarity:
                    best_similarity = final_similarity
                    best_project = proj

                if final_similarity >= 60:
                    duplicate_found = True
                    break

            if duplicate_found:
                request.session['duplicate_warning'] = (
                    f"⚠️ Duplicate detected! Similarity Score: {best_similarity}%. "
                    f"Similar to: '{best_project.title}' approved for {best_project.student.full_name} "
                    f"(Guide: {best_project.reviewed_by.full_name if best_project.reviewed_by else 'N/A'})."
                )
                messages.warning(request, "⚠️ This project is too similar to an already approved one.")
                return redirect("student_dashboard")

            # ---- Save project ----
            project = form.save(commit=False)
            project.student = student
            project.status = "Pending"
            project.created_at = timezone.now()
            project.save()

            messages.success(request, "✔ Project submitted successfully! Awaiting teacher approval.")
            return redirect("student_dashboard")

    return render(request, 'student_dashboard.html', {
        'student': student,
        'form': form,
        'submitted_projects': submitted_projects,
        'deadline_info': deadline_info,
        'deadline_passed': deadline_passed,
        'teacher_removed': teacher_removed,
        'teacher_name': teacher_name,
        'duplicate_warning': request.session.get('duplicate_warning'),
    })



# -------------------- EDIT / DELETE PROJECT --------------------
def edit_project(request, project_id):
    project = get_object_or_404(Projectsubmission, id=project_id)
    student_id = request.session.get('user_id')

    if project.student.id != student_id:
        messages.error(request, "Unauthorized access.")
        return redirect('student_dashboard')

    if project.status == "Approved":
        messages.warning(request, "You cannot edit an approved project.")
        return redirect('student_dashboard')

    if request.method == 'POST':
        form = ProjectSubmissionForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Project updated successfully!")
            return redirect('student_dashboard')
    else:
        form = ProjectSubmissionForm(instance=project)

    return render(request, 'edit_project.html', {'form': form, 'project': project})


def delete_project(request, project_id):
    project = get_object_or_404(Projectsubmission, id=project_id)
    student_id = request.session.get('user_id')

    if project.student.id != student_id:
        messages.error(request, "Unauthorized access.")
        return redirect('student_dashboard')

    if request.method == "POST":
        if project.status == "Approved":
            messages.warning(request, "You cannot delete an approved project.")
            return redirect('student_dashboard')

        project.delete()
        messages.success(request, "🗑️ Project deleted successfully!")
        return redirect('student_dashboard')

    messages.error(request, "Invalid request method.")
    return redirect('student_dashboard')


# -------------------- SUBMIT PROJECT --------------------
def submit_project(request):
    student_id = request.session.get('user_id')
    role = request.session.get('role')

    if not student_id or role != 'student':
        messages.error(request, "Unauthorized access.")
        return redirect('login_page')

    student = get_object_or_404(UserRegistration, id=student_id)
    latest_deadline = SubmissionDeadline.objects.order_by('-created_at').first()

    if latest_deadline and timezone.now().date() > latest_deadline.deadline:
        return render(request, 'submit_blocked.html', {
            'student': student,
            'message': "⏰ The project submission deadline has passed. You cannot submit a new project.",
            'color': "#ef4444"
        })

    existing_project = Projectsubmission.objects.filter(
        student=student,
        status__in=['Pending', 'Approved']
    ).first()

    if existing_project:
        msg = "✅ Your project has already been approved." if existing_project.status == "Approved" else "⚠️ You already have a project under review. Please wait for the teacher's decision."
        color = "#16a34a" if existing_project.status == "Approved" else "#f59e0b"
        return render(request, 'submit_blocked.html', {'student': student, 'message': msg, 'color': color})

    if request.method == 'POST':
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.student = student
            project.status = 'Pending'
            project.created_at = timezone.now()

       
            # 🚨 DUPLICATE CHECK (RapidFuzz)
            approved_projects = Projectsubmission.objects.filter(status='Approved')

            for approved in approved_projects:
                title_similarity = fuzz.token_sort_ratio(project.title.lower(), approved.title.lower())
                desc_similarity = fuzz.token_sort_ratio(project.description.lower(), approved.description.lower())

                if title_similarity > 75 or desc_similarity > 75:
                    messages.error(
                        request,
                        f"⚠️ This project is too similar to '{approved.title}', "
                        f"which was already approved for {approved.student.full_name}. "
                        f"Please modify your project idea."
                    )
                    return redirect('student_dashboard')

            # ✅ If no duplicates found, save project
            project.save()
            messages.success(request, "✅ Project idea submitted successfully! Awaiting teacher review.")
            return redirect('student_dashboard')
        else:
            messages.error(request, "⚠️ Please fill out all required fields before submitting.")
    else:
        form = ProjectSubmissionForm()

    return render(request, 'submit_project.html', {'form': form})

# -------------------- CHECK PROJECT STATUS (AJAX) --------------------
def check_project_status(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return JsonResponse({'status': 'None'})

    student = get_object_or_404(UserRegistration, id=user_id)
    project = Projectsubmission.objects.filter(student=student).order_by('-created_at').first()
    return JsonResponse({'status': project.status if project else 'None'})


# -------------------- TEACHER DASHBOARD --------------------


def teacher_dashboard(request):
    if not request.session.get('user_id'):
        return redirect('login_page')

    # ❌ Block non-teachers
    if request.session.get("role") != "teacher":
        return redirect("login_page")


    teacher = get_object_or_404(UserRegistration, id=request.session['user_id'])
    assigned_students = UserRegistration.objects.filter(
        role='student',
        assigned_teacher=teacher,
        is_verified=True
    )

    submitted_projects = Projectsubmission.objects.filter(
        student__in=assigned_students
    ).order_by('-id')

    # ---------------- DEADLINE INFO ----------------
    latest_deadline = SubmissionDeadline.objects.order_by('-created_at').first()
    student_deadline_info = None
    review_info = None
    review_passed = False

    today = date.today()

    if latest_deadline and latest_deadline.deadline:
        days_left_student = (latest_deadline.deadline - today).days

        if days_left_student > 1:
            student_deadline_info = {'text': f"🕒 Students have {days_left_student} days left.", 'color': '#2563eb'}
        elif days_left_student == 1:
            student_deadline_info = {'text': "⚠️ Students' last day is tomorrow!", 'color': '#f59e0b'}
        elif days_left_student == 0:
            student_deadline_info = {'text': "🚨 Today is final submission day!", 'color': '#eab308'}
        else:
            student_deadline_info = {'text': "❌ Student submission deadline passed.", 'color': '#dc2626'}

    if latest_deadline and latest_deadline.teacher_deadline:
        review_days_left = (latest_deadline.teacher_deadline - today).days

        if review_days_left > 1:
            review_info = {'text': f"✅ {review_days_left} days left to review.", 'color': '#16a34a'}
        elif review_days_left == 1:
            review_info = {'text': "⚠️ Review last day is tomorrow!", 'color': '#f59e0b'}
        elif review_days_left == 0:
            review_info = {'text': "🚨 Today is final review day!", 'color': '#eab308'}
        else:
            review_info = {'text': "❌ Review deadline passed.", 'color': '#dc2626'}
            review_passed = True

    # ---------------- DUPLICATE CHECK ----------------
    duplicate_warnings = {}
    
    pending_projects = submitted_projects.filter(status="Pending")
    all_other_projects = Projectsubmission.objects.exclude(id__isnull=True)

    for project in pending_projects:
        warnings = []
        text1 = f"{project.title} {project.description} {project.technology_used}".lower()
        model = get_sbert_model()
        emb1 = model.encode(text1, convert_to_tensor=True)


        for other in all_other_projects:
            if other.id == project.id:
                continue

            text2 = f"{other.title} {other.description} {other.technology_used}".lower()
            model = get_sbert_model()
            emb2 = model.encode(text2, convert_to_tensor=True)

            semantic = float(util.cos_sim(emb1, emb2)[0][0]) * 100
            token = fuzz.WRatio(text1, text2)
            score = round((semantic * 0.6) + (token * 0.4))

            if score >= 60:
                warnings.append({
                    "other_student": other.student.full_name,
                    "other_title": other.title,
                    "similarity": score,
                    "guide": other.student.assigned_teacher.full_name if other.student.assigned_teacher else "N/A",
                    "status": other.status
                })

        if warnings:
            duplicate_warnings[project.id] = warnings

    return render(request, 'teacher_dashboard.html', {
        'full_name': teacher.full_name,
        'role': 'Teacher',
        'assigned_students': assigned_students,
        'submitted_projects': submitted_projects,
        'student_deadline_info': student_deadline_info,
        'review_info': review_info,
        'review_passed': review_passed,
        'duplicate_warnings': duplicate_warnings,
    })


# -------------------- APPROVE PROJECT --------------------
@require_POST
def approve_project(request, project_id):
    teacher_id = request.session.get('user_id')
    role = request.session.get('role')

    if not teacher_id or role != 'teacher':
        messages.error(request, "Unauthorized access.")
        return redirect('login_page')
    
     # 🔒 Enforce teacher deadline
    latest_deadline = SubmissionDeadline.objects.order_by('-created_at').first()
    if latest_deadline and latest_deadline.teacher_deadline and \
    date.today() > latest_deadline.teacher_deadline:
        messages.warning(request, "⏰ Review deadline has passed. You can no longer approve projects.")
        return redirect('teacher_dashboard')

    teacher = get_object_or_404(UserRegistration, id=teacher_id)
    project = get_object_or_404(Projectsubmission, id=project_id)

    if project.student.assigned_teacher_id != teacher_id:
        messages.error(request, "You are not assigned as the guide for this student.")
        return redirect('teacher_dashboard')

    project.status = "Approved"
    project.reviewed_by = teacher
    project.reviewed_at = timezone.now()
    project.save()

    Projectsubmission.objects.filter(student=project.student, status="Pending").exclude(id=project.id).update(status="Rejected")

    messages.success(request, f"✅ Project '{project.title}' has been approved successfully!")
    return redirect('teacher_dashboard')

# ------------------ Reject Project-----------------------------
@require_POST
def reject_project(request, project_id):
    teacher_id = request.session.get('user_id')
    role = request.session.get('role')

    if not teacher_id or role != 'teacher':
        messages.error(request, "Unauthorized access.")
        return redirect('login_page')

    # 🔒 Enforce teacher deadline
    latest_deadline = SubmissionDeadline.objects.order_by('-created_at').first()
    if latest_deadline and latest_deadline.teacher_deadline and \
    date.today() > latest_deadline.teacher_deadline:
        messages.warning(request, "⏰ Review deadline has passed. You can no longer reject projects.")
        return redirect('teacher_dashboard')

    teacher = get_object_or_404(UserRegistration, id=teacher_id)
    project = get_object_or_404(Projectsubmission, id=project_id)

    # ✅ Ensure the teacher is assigned to this student
    if project.student.assigned_teacher_id != teacher_id:
        messages.error(request, "You are not assigned as the guide for this student.")
        return redirect('teacher_dashboard')

    # ✅ Update project details
    project.status = "Rejected"
    project.reviewed_by = teacher
    project.reviewed_at = timezone.now()
    project.save()

    messages.warning(request, f"❌ Project '{project.title}' has been rejected successfully.")
    return redirect('teacher_dashboard')


# -------------------- FEEDBACK SUBMISSION --------------------
@require_POST
def handle_project_feedback(request):
    project_id = request.POST.get('project_id')
    action = request.POST.get('action')
    feedback = request.POST.get('feedback', '').strip()

    project = get_object_or_404(Projectsubmission, id=project_id)
    teacher_id = request.session.get('user_id')

    if project.student.assigned_teacher_id != teacher_id:
        messages.error(request, "Unauthorized access.")
        return redirect('teacher_dashboard')

    if action == "approve":
        project.status = "Approved"
        messages.success(request, f"✅ Project '{project.title}' approved.")
    elif action == "reject":
        project.status = "Rejected"
        messages.warning(request, f"❌ Project '{project.title}' rejected.")

    project.feedback = feedback
    project.save()
    return redirect('teacher_dashboard')


# -------------------- ADMIN DASHBOARD --------------------
def admin_dashboard(request):
    user_id = request.session.get('user_id')
    role = request.session.get('role')

    if not user_id or role != 'admin':
        messages.error(request, "You must be logged in as admin to view this page.")
        return redirect('login_page')

    pending_teachers = UserRegistration.objects.filter(
        role='teacher', is_verified=False, is_deleted=False
    )
    pending_students = UserRegistration.objects.filter(
        role='student', is_verified=False, is_deleted=False
    )
    verified_teachers = UserRegistration.objects.filter(
        role='teacher', is_verified=True, is_deleted=False
    )
    verified_students = UserRegistration.objects.filter(
        role='student', is_verified=True, is_deleted=False
    )
    deleted_users = UserRegistration.objects.filter(is_deleted=True)

 # ✅ Fetch approved projects with teacher and student details
    approved_projects = Projectsubmission.objects.filter(status="Approved").select_related('student', 'reviewed_by')

    # Group projects by teacher
    teacher_project_map = {}
    for project in approved_projects:
        teacher = project.reviewed_by
        if teacher not in teacher_project_map:
            teacher_project_map[teacher] = []
        teacher_project_map[teacher].append(project)

    return render(request, 'admin_dashboard.html', {
        'pending_teachers': pending_teachers,
        'pending_students': pending_students,
        'verified_teachers': verified_teachers,
        'verified_students': verified_students,
        'deleted_users': deleted_users,
        'teacher_project_map': teacher_project_map,
    })


# -------------------- ASSIGN / REASSIGN TEACHER --------------------
def assign_teacher(request, student_id):
    user_id = request.session.get('user_id')
    role = request.session.get('role')

    if not user_id or role != 'admin':
        messages.error(request, "Unauthorized access.")
        return redirect('login_page')

    student = get_object_or_404(UserRegistration, id=student_id, role='student',is_deleted=False)

    if request.method == "POST":
        teacher_id = request.POST.get('teacher_id')
        if not teacher_id:
            student.assigned_teacher = None
            student.save()
            messages.success(request, f"Guide removed from {student.full_name}")
            return redirect('admin_dashboard')

        teacher = get_object_or_404(UserRegistration, id=teacher_id, role='teacher', is_deleted=False)
        student.assigned_teacher = teacher
        student.save()
        messages.success(request, f"Guide assigned: {teacher.full_name} → {student.full_name}")
        return redirect('admin_dashboard')

    messages.error(request, "Invalid request method.")
    return redirect('admin_dashboard')


# -------------------- MANAGE USERS --------------------
def manage_users(request):
    if request.session.get('role') != 'admin':
        messages.error(request, "You are not authorized to view this page.")
        return redirect('login_page')

    approved_students = UserRegistration.objects.filter(role='student', is_verified=True, is_deleted=False)
    approved_teachers = UserRegistration.objects.filter(role='teacher', is_verified=True, is_deleted=False)

    return render(request, 'admin_manage_users.html', {
        'approved_students': approved_students,
        'approved_teachers': approved_teachers,
        'verified_teachers': approved_teachers,
        'verified_students': approved_students
    })


def delete_user(request, user_id):
    if not request.session.get('user_id'):
        messages.error(request, "You must be logged in first.")
        return redirect('login_page')

    if request.session.get('role') != 'admin':
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    user = get_object_or_404(UserRegistration, id=user_id)

    # 🚫 If already deleted
    if user.is_deleted:
        messages.info(request, f"{user.full_name} is already deleted.")
        return redirect('admin_dashboard')

    # 🧑‍🏫 If the deleted user is a teacher, unassign them from all students
    if user.role == 'teacher':
        assigned_students = UserRegistration.objects.filter(assigned_teacher=user)
        for student in assigned_students:
            student.assigned_teacher = None
            student.save()
        messages.info(request, f"🧑‍🏫 All students previously guided by {user.full_name} have been unassigned.")

    # 🗑️ Soft delete the user
    user.is_deleted = True
    user.deleted_at = timezone.now()
    user.save()

    messages.success(request, f"🗑️ {user.full_name} has been soft-deleted successfully.")
    return redirect('admin_dashboard')
def restore_user(request, user_id):
    if not request.session.get('user_id'):
        messages.error(request, "You must be logged in first.")
        return redirect('login_page')

    if request.session.get('role') != 'admin':
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    user = get_object_or_404(UserRegistration, id=user_id)
    user.is_deleted = False
    user.save()

    messages.success(request, f"♻️ {user.full_name} has been restored successfully.")
    return redirect('admin_dashboard')


# -------------------- SET SUBMISSION DEADLINE --------------------
def set_submission_deadline(request):
    if request.session.get('role') != 'admin':
        messages.error(request, "Unauthorized access.")
        return redirect('login_page')

    latest_deadline = SubmissionDeadline.objects.order_by('-created_at').first()

    if request.method == 'POST':
        form = SubmissionDeadlineForm(request.POST, instance=latest_deadline)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Student and Teacher deadlines updated successfully!")
            return redirect('set_deadline')
    else:
        form = SubmissionDeadlineForm(instance=latest_deadline)

    return render(request, 'admin_set_deadline.html', {
        'form': form,
        'deadline': latest_deadline,
    })



# -------------------- REGISTER --------------------
def register_page(request):
    request.session.flush()

    if request.method == "POST":
        full_name = request.POST.get("name")
        email = request.POST.get("email")
        role = request.POST.get("role")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirmPassword")

        # Student-specific fields
        department = request.POST.get("department")  # from student form
        year_of_study = request.POST.get("year_of_study")
        roll_no = request.POST.get("roll_no")

        # Teacher-specific fields
        dept = request.POST.get("dept")
        designation = request.POST.get("designation")

        # Password validation
        if password != confirm_password:
            messages.error(request, "❌ Passwords do not match!")
            return redirect('register_page')

        if UserRegistration.objects.filter(email=email).exists():
            messages.error(request, "⚠️ Email already registered!")
            return redirect('register_page')

        # Auto-verify admins only
        is_verified = True if role == 'admin' else False

        # Create user object
        user = UserRegistration(
            full_name=full_name,
            email=email,
            role=role,
            is_verified=is_verified
        )

        # 🔒 Save password securely
        user.set_password(password)

        # ✅ Assign extra fields depending on role
        if role == 'student':
            user.course = year_of_study or None
            user.student_id = roll_no or None
            user.dept = department or None

        elif role == 'teacher':
            user.dept = dept or None
            user.designation = designation or None

        # Save user
        user.save()

        # Success message
        if role == 'admin':
            msg = "✅ Admin registered successfully! You can log in now."
        else:
            msg = "🎉 Registration successful! Please wait for admin verification."

        messages.success(request, msg)
        return redirect('login_page')

    return render(request, 'registration.html')


# -------------------- LOGOUT --------------------
def logout_page(request):
    request.session.flush()
    messages.success(request, "Logged out successfully!")
    return redirect('home')


# -------------------- APPROVE / REJECT USER --------------------
def approve_user(request, user_id):
    user = get_object_or_404(UserRegistration, id=user_id)
    user.is_verified = True
    user.save()
    messages.success(request, f"{user.full_name} has been approved successfully.")
    return redirect('admin_dashboard')


def reject_user(request, user_id):
    user = get_object_or_404(UserRegistration, id=user_id)
    messages.info(request, f"{user.full_name} has been rejected and removed.")
    user.delete()
    return redirect('admin_dashboard')


# -------------------- ABOUT PAGE --------------------
def about(request):
    return render(request, 'about.html')


# -------------------- PROFILE PAGE --------------------
def profile_page(request):
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('login_page')

    user = get_object_or_404(UserRegistration, id=user_id)
    form = EditProfileForm(instance=user)

    if request.method == "POST":
        form = EditProfileForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save(commit=False)
            if form.cleaned_data['password']:
                user.password = make_password(form.cleaned_data['password'])
            user.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')

    return render(request, 'profile.html', {'user': user, 'form': form})
