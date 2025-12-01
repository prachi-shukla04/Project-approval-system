from django.test import TestCase, Client
from django.urls import reverse, resolve
from django.utils import timezone
from datetime import date, timedelta

from main_app.models import (
    UserRegistration,
    Project,
    Projectsubmission,
    SubmissionDeadline
)
from main_app import views


# =====================================================================
# 🌟 PROJECT SUBMISSION & TEACHER LOGIC TESTS
# =====================================================================
class ProjectApprovalTests(TestCase):

    def setUp(self):
        self.client = Client()

        # Admin
        self.admin = UserRegistration.objects.create(
            full_name="Admin",
            email="admin@test.com",
            role="admin",
            is_verified=True
        )
        self.admin.set_password("admin123")
        self.admin.save()

        # Teacher A
        self.teacher = UserRegistration.objects.create(
            full_name="Teacher One",
            email="t1@test.com",
            role="teacher",
            dept="CSE",
            designation="Assistant Professor",
            is_verified=True
        )
        self.teacher.set_password("teacher123")
        self.teacher.save()

        # Teacher B
        self.other_teacher = UserRegistration.objects.create(
            full_name="Teacher Two",
            email="t2@test.com",
            role="teacher",
            is_verified=True
        )
        self.other_teacher.set_password("teacher456")
        self.other_teacher.save()

        # Student A
        self.student = UserRegistration.objects.create(
            full_name="Student A",
            email="s1@test.com",
            role="student",
            assigned_teacher=self.teacher,
            is_verified=True
        )
        self.student.set_password("stud123")
        self.student.save()

        # Default Deadline
        self.deadline = SubmissionDeadline.objects.create(
            deadline=date.today() + timedelta(days=2),
            teacher_deadline=date.today() + timedelta(days=2)
        )

    # Helpers
    def login_teacher(self):
        self.client.post(reverse("login_page"), {
            "email": "t1@test.com",
            "password": "teacher123",
            "role": "teacher"
        })

    def login_student(self):
        self.client.post(reverse("login_page"), {
            "email": "s1@test.com",
            "password": "stud123",
            "role": "student"
        })

    # -----------------------------------------------------------
    # 1️⃣ Teacher Approves Assigned Student Project
    # -----------------------------------------------------------
    def test_teacher_approves_project(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="AI Project",
            description="Desc",
            technology_used="Python"
        )

        self.login_teacher()
        self.client.post(reverse("approve_project", args=[project.id]))

        project.refresh_from_db()
        self.assertEqual(project.status, "Approved")
        self.assertEqual(project.reviewed_by, self.teacher)

    # -----------------------------------------------------------
    # 2️⃣ Other Teacher Cannot Approve Project
    # -----------------------------------------------------------
    def test_other_teacher_cannot_approve(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="ML Project",
            description="Desc A",
            technology_used="Python",
        )

        self.client.post(reverse("login_page"), {
            "email": "t2@test.com",
            "password": "teacher456",
            "role": "teacher",
        })

        self.client.post(reverse("approve_project", args=[project.id]))

        project.refresh_from_db()
        self.assertEqual(project.status, "Pending")

    # -----------------------------------------------------------
    # 3️⃣ Student Duplicate Block (Approved Project)
    # -----------------------------------------------------------
    def test_duplicate_project_block(self):
        Projectsubmission.objects.create(
            student=self.student,
            title="Face Recognition System",
            description="AI based",
            technology_used="Python",
            status="Approved",
            reviewed_by=self.teacher
        )

        self.login_student()

        response = self.client.post(
            reverse("student_dashboard"),
            {
                "title": "Face Recognition",
                "description": "AI based system",
                "technology_used": "Python"
            },
            follow=True
        )

        self.assertContains(response, "duplicate")

    # -----------------------------------------------------------
    # 4️⃣ Cannot Submit After Deadline
    # -----------------------------------------------------------
    def test_submission_after_deadline_blocked(self):
        self.deadline.deadline = date.today() - timedelta(days=1)
        self.deadline.save()

        self.login_student()

        response = self.client.post(reverse("student_dashboard"), {
            "title": "New Project",
            "description": "Desc",
            "technology_used": "HTML"
        }, follow=True)

        self.assertEqual(response.status_code, 200)

        exists = Projectsubmission.objects.filter(
            student=self.student,
            title="New Project"
        ).exists()

        self.assertFalse(exists)

    # -----------------------------------------------------------
    # 5️⃣ Student Cannot Edit Approved Project
    # -----------------------------------------------------------
    def test_student_cannot_edit_approved_project(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="Old Title",
            description="Old Desc",
            technology_used="Python",
            status="Approved",
            reviewed_by=self.teacher
        )

        self.login_student()

        response = self.client.post(reverse("update_project", args=[project.id]), {
            "title": "New Title",
            "description": "New Desc",
            "technology_used": "React"
        })

        project.refresh_from_db()
        self.assertEqual(project.title, "Old Title")
        self.assertEqual(response.status_code, 302)

    # -----------------------------------------------------------
    # 6️⃣ Student Cannot Delete Approved Project
    # -----------------------------------------------------------
    def test_student_cannot_delete_approved(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="Del Test",
            description="Desc",
            technology_used="Java",
            status="Approved",
        )

        self.login_student()
        self.client.post(reverse("delete_project", args=[project.id]))

        self.assertTrue(Projectsubmission.objects.filter(id=project.id).exists())

    # -----------------------------------------------------------
    # 7️⃣ Teacher Cannot Approve After Review Deadline
    # -----------------------------------------------------------
    def test_teacher_cannot_approve_after_deadline(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="Late Project",
            description="Desc",
            technology_used="C"
        )

        self.deadline.teacher_deadline = date.today() - timedelta(days=1)
        self.deadline.save()

        self.login_teacher()
        response = self.client.post(reverse("approve_project", args=[project.id]), follow=True)

        project.refresh_from_db()
        self.assertEqual(project.status, "Pending")
        self.assertContains(response, "Review deadline")

    # -----------------------------------------------------------
    # 8️⃣ Student Dashboard Loads
    # -----------------------------------------------------------
    def test_student_dashboard_loads(self):
        self.login_student()
        response = self.client.get(reverse("student_dashboard"))
        self.assertContains(response, self.teacher.full_name)

    # -----------------------------------------------------------
    # 9️⃣ Student Cannot Submit if Teacher Deleted
    # -----------------------------------------------------------
    def test_student_cannot_submit_if_teacher_deleted(self):
        self.teacher.is_deleted = True
        self.teacher.save()

        self.login_student()

        response = self.client.post(reverse("student_dashboard"), {
            "title": "Proj",
            "description": "Test",
            "technology_used": "Python"
        }, follow=True)

        self.assertContains(response, "removed")

    # -----------------------------------------------------------
    # 🔟 Duplicate Warning Displayed on Dashboard
    # -----------------------------------------------------------
    def test_duplicate_warning_message_display(self):
        session = self.client.session
        session["duplicate_warning"] = "Duplicate test message"
        session.save()

        self.login_student()
        response = self.client.get(reverse("student_dashboard"))

        self.assertContains(response, "Duplicate test message")

    # -----------------------------------------------------------
    # 1️⃣1️⃣ Student Cannot Submit When Pending Exists
    # -----------------------------------------------------------
    def test_student_cannot_submit_when_pending_exists(self):
        Projectsubmission.objects.create(
            student=self.student,
            title="Pending Project",
            description="Existing",
            technology_used="Python",
            status="Pending"
        )

        self.login_student()

        response = self.client.post(reverse("student_dashboard"), {
            "title": "Test New",
            "description": "Trying to submit",
            "technology_used": "Java"
        })

        self.assertEqual(response.status_code, 302)

        total = Projectsubmission.objects.filter(student=self.student).count()
        self.assertEqual(total, 1)

    # -----------------------------------------------------------
    # 1️⃣2️⃣ Teacher Dashboard Shows Only Assigned Students
    # -----------------------------------------------------------
    def test_teacher_dashboard_shows_only_assigned_students(self):
        student2 = UserRegistration.objects.create(
            full_name="Another Student",
            email="other@test.com",
            role="student",
            is_verified=True
        )

        self.login_teacher()
        response = self.client.get(reverse("teacher_dashboard"))

        self.assertContains(response, self.student.full_name)
        self.assertNotContains(response, student2.full_name)

    # -----------------------------------------------------------
    # 1️⃣3️⃣ Teacher Should NOT Approve Unassigned Student
    # -----------------------------------------------------------
    def test_teacher_cannot_approve_unassigned_student(self):
        student2 = UserRegistration.objects.create(
            full_name="S2",
            email="s2@test.com",
            role="student",
            is_verified=True
        )

        project = Projectsubmission.objects.create(
            student=student2,
            title="Not Yours",
            description="D",
            technology_used="Python"
        )

        self.login_teacher()
        self.client.post(reverse("approve_project", args=[project.id]))

        project.refresh_from_db()
        self.assertEqual(project.status, "Pending")

    # -----------------------------------------------------------
    # 1️⃣4️⃣ Delete Requires POST
    # -----------------------------------------------------------
    def test_delete_project_requires_post(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="Test",
            description="D",
            technology_used="C"
        )

        self.login_student()
        self.client.get(reverse("delete_project", args=[project.id]))

        self.assertTrue(Projectsubmission.objects.filter(id=project.id).exists())

    # -----------------------------------------------------------
    # 1️⃣5️⃣ ROLE-BASED ACCESS: Student cannot open teacher dashboard
    # -----------------------------------------------------------
    def test_student_cannot_access_teacher_dashboard(self):
        self.login_student()
        response = self.client.get(reverse("teacher_dashboard"))
        self.assertNotEqual(response.status_code, 200)

    # -----------------------------------------------------------
    # 1️⃣6️⃣ ROLE-BASED ACCESS: Teacher cannot open admin dashboard
    # -----------------------------------------------------------
    def test_teacher_cannot_access_admin_dashboard(self):
        self.login_teacher()
        response = self.client.get(reverse("admin_dashboard"))
        self.assertNotEqual(response.status_code, 200)

    # -----------------------------------------------------------
    # 1️⃣7️⃣ Student Cannot Approve Project
    # -----------------------------------------------------------
    def test_student_cannot_approve_project(self):
        project = Projectsubmission.objects.create(
            student=self.student,
            title="XYZ",
            description="Desc",
            technology_used="Py"
        )

        self.login_student()
        self.client.post(reverse("approve_project", args=[project.id]))

        project.refresh_from_db()
        self.assertEqual(project.status, "Pending")

    # -----------------------------------------------------------
    # 1️⃣8️⃣ Invalid Login Rejected
    # -----------------------------------------------------------
    def test_invalid_login_rejected(self):
        response = self.client.post(reverse("login_page"), {
            "email": "s1@test.com",
            "password": "wrongpass",
            "role": "student"
        })

        self.assertNotIn("user_id", self.client.session)

    # -----------------------------------------------------------
    # 1️⃣9️⃣ Teacher Duplicate Similarity Alert (Pending-Pending)
    # -----------------------------------------------------------
    def test_teacher_duplicate_similarity_alert(self):
        Projectsubmission.objects.create(
            student=self.student,
            title="AI Drone System",
            description="Drone using AI",
            technology_used="Python",
            status="Pending"
        )

        student2 = UserRegistration.objects.create(
            full_name="Student B",
            email="b@test.com",
            role="student",
            assigned_teacher=self.teacher,
            is_verified=True
        )

        Projectsubmission.objects.create(
            student=student2,
            title="AI Drone",
            description="Drone automation",
            technology_used="Python",
            status="Pending"
        )

        self.login_teacher()
        response = self.client.get(reverse("teacher_dashboard"))

        self.assertContains(response, "Similar")


# =====================================================================
# 🌟 MODELS TESTS
# =====================================================================
class UserRegistrationModelTests(TestCase):

    def test_create_student_user(self):
        student = UserRegistration.objects.create(
            full_name="Student Example",
            email="student@test.com",
            role="student",
            student_id="101",
            course="BCA",
            dept="CSE",
            is_verified=True
        )
        self.assertEqual(student.full_name, "Student Example")
        self.assertEqual(student.role, "student")
        self.assertTrue(student.is_verified)
        self.assertEqual(str(student), "Student Example (student)")

    def test_password_hashing(self):
        user = UserRegistration(
            full_name="Prachi",
            email="prachi@test.com",
            role="student"
        )
        user.set_password("mypassword")
        user.save()

        self.assertNotEqual(user.password, "mypassword")
        self.assertTrue(user.check_password("mypassword"))

    def test_soft_delete_flag(self):
        teacher = UserRegistration.objects.create(
            full_name="Deleted Teacher",
            email="del@test.com",
            role="teacher"
        )
        teacher.is_deleted = True
        teacher.deleted_at = timezone.now()
        teacher.save()

        self.assertTrue(teacher.is_deleted)
        self.assertIsNotNone(teacher.deleted_at)


class ProjectModelTests(TestCase):
    def setUp(self):
        self.student = UserRegistration.objects.create(
            full_name="Student A",
            email="s1@test.com",
            role="student",
            is_verified=True
        )

    def test_project_creation(self):
        project = Project.objects.create(
            student=self.student,
            title="AI System",
            description="Desc"
        )

        self.assertEqual(project.title, "AI System")
        self.assertEqual(project.student.full_name, "Student A")
        self.assertFalse(project.approved)
        self.assertIn("AI System", str(project))


class ProjectSubmissionModelTests(TestCase):
    def setUp(self):
        self.teacher = UserRegistration.objects.create(
            full_name="Teacher One",
            email="t1@test.com",
            role="teacher",
            is_verified=True
        )
        self.student = UserRegistration.objects.create(
            full_name="Student One",
            email="s1@test.com",
            role="student",
            assigned_teacher=self.teacher,
            is_verified=True
        )

    def test_submission_defaults(self):
        sub = Projectsubmission.objects.create(
            student=self.student,
            title="ML Project",
            description="desc",
            technology_used="Python"
        )

        self.assertEqual(sub.status, "Pending")
        self.assertIsNone(sub.reviewed_by)
        self.assertIsNotNone(sub.created_at)
        self.assertIn("ML Project", str(sub))

    def test_submission_approval(self):
        sub = Projectsubmission.objects.create(
            student=self.student,
            title="AI Project",
            description="desc",
            technology_used="Python"
        )

        sub.status = "Approved"
        sub.reviewed_by = self.teacher
        sub.reviewed_at = timezone.now()
        sub.feedback = "Good work"
        sub.save()

        self.assertEqual(sub.status, "Approved")
        self.assertEqual(sub.reviewed_by, self.teacher)
        self.assertIsNotNone(sub.reviewed_at)
        self.assertEqual(sub.feedback, "Good work")

    def test_team_members_optional(self):
        sub = Projectsubmission.objects.create(
            student=self.student,
            title="Group Project",
            description="desc",
            technology_used="React",
            team_members="Prachi, Rahul"
        )

        self.assertEqual(sub.team_members, "Prachi, Rahul")


class SubmissionDeadlineModelTests(TestCase):

    def test_deadline_creation(self):
        deadline = SubmissionDeadline.objects.create(
            deadline=date.today() + timedelta(days=2),
            teacher_deadline=date.today() + timedelta(days=4),
        )

        self.assertIn("Student Deadline", str(deadline))
        self.assertEqual(
            (deadline.teacher_deadline - deadline.deadline).days,
            2
        )

    def test_deadline_teacher_optional(self):
        deadline = SubmissionDeadline.objects.create(
            deadline=date.today() + timedelta(days=2)
        )
        self.assertIsNone(deadline.teacher_deadline)


# =====================================================================
# 🌟 URL TESTS
# =====================================================================
class URLTests(TestCase):

    def test_home_url(self):
        url = reverse('home')
        self.assertEqual(resolve(url).func, views.home)

    def test_register_url(self):
        url = reverse('register_page')
        self.assertEqual(resolve(url).func, views.register_page)

    def test_login_url(self):
        url = reverse('login_page')
        self.assertEqual(resolve(url).func, views.login_page)

    def test_logout_url(self):
        url = reverse('logout')
        self.assertEqual(resolve(url).func, views.logout_page)

    def test_index_url(self):
        url = reverse('index')
        self.assertEqual(resolve(url).func, views.index)

    def test_about_url(self):
        url = reverse('about')
        self.assertEqual(resolve(url).func, views.about)

    def test_profile_url(self):
        url = reverse('profile')
        self.assertEqual(resolve(url).func, views.profile_page)

    # Student URLs
    def test_student_dashboard_url(self):
        url = reverse('student_dashboard')
        self.assertEqual(resolve(url).func, views.student_dashboard)

    def test_submit_project_url(self):
        url = reverse('submit_project')
        self.assertEqual(resolve(url).func, views.submit_project)

    def test_edit_project_url(self):
        url = reverse('update_project', args=[5])
        self.assertEqual(resolve(url).func, views.edit_project)

    def test_delete_project_url(self):
        url = reverse('delete_project', args=[10])
        self.assertEqual(resolve(url).func, views.delete_project)

    def test_check_project_status_url(self):
        url = reverse('check_project_status')
        self.assertEqual(resolve(url).func, views.check_project_status)

    # Teacher URLs
    def test_teacher_dashboard_url(self):
        url = reverse('teacher_dashboard')
        self.assertEqual(resolve(url).func, views.teacher_dashboard)

    def test_approve_project_url(self):
        url = reverse('approve_project', args=[7])
        self.assertEqual(resolve(url).func, views.approve_project)

    def test_reject_project_url(self):
        url = reverse('reject_project', args=[3])
        self.assertEqual(resolve(url).func, views.reject_project)

    def test_teacher_feedback_url(self):
        url = reverse('handle_project_feedback')
        self.assertEqual(resolve(url).func, views.handle_project_feedback)

    # Admin URLs
    def test_admin_dashboard_url(self):
        url = reverse('admin_dashboard')
        self.assertEqual(resolve(url).func, views.admin_dashboard)

    def test_admin_approve_user_url(self):
        url = reverse('approve_user', args=[2])
        self.assertEqual(resolve(url).func, views.approve_user)

    def test_admin_reject_user_url(self):
        url = reverse('reject_user', args=[4])
        self.assertEqual(resolve(url).func, views.reject_user)

    def test_assign_teacher_url(self):
        url = reverse('assign_teacher', args=[6])
        self.assertEqual(resolve(url).func, views.assign_teacher)

    def test_manage_users_url(self):
        url = reverse('manage_users')
        self.assertEqual(resolve(url).func, views.manage_users)

    def test_delete_user_url(self):
        url = reverse('delete_user', args=[9])
        self.assertEqual(resolve(url).func, views.delete_user)

    def test_set_deadline_url(self):
        url = reverse('set_deadline')
        self.assertEqual(resolve(url).func, views.set_submission_deadline)

    def test_restore_user_url(self):
        url = reverse('restore_user', args=[11])
        self.assertEqual(resolve(url).func, views.restore_user)
# =====================================================================