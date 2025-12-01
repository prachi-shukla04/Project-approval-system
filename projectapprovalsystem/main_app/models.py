from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone


# -------------------- USER REGISTRATION MODEL --------------------
class UserRegistration(models.Model):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('admin', 'Admin'),
    ]

    # Common Fields
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    password = models.CharField(max_length=255)

    # Student-specific
    student_id = models.CharField(max_length=50, null=True, blank=True)
    course = models.CharField(max_length=100, null=True, blank=True)
    interest = models.CharField(max_length=200, null=True, blank=True)

    # Teacher-specific
    dept = models.CharField(max_length=100, null=True, blank=True)
    designation = models.CharField(max_length=100, null=True, blank=True)

   

    # Verification fields
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    # Teacher assignment (admin assigns teacher to student)
    assigned_teacher = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'teacher'},
        related_name='assigned_students'
    )
    status = models.CharField(
        max_length=20,
        default="Pending",
        choices=[
            ("Pending", "Pending"),
            ("Approved", "Approved"),
            ("Rejected", "Rejected"),
        ],
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    

     # ✅ Soft delete flag
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    def __str__(self):
        return f"{self.full_name} ({self.role})"

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)


# -------------------- PROJECT MODEL --------------------
class Project(models.Model):
    student = models.ForeignKey(
        'UserRegistration',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='projects',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    file = models.FileField(upload_to='projects/', blank=True, null=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} by {self.student.full_name}"


# -------------------- PROJECT SUBMISSION MODEL --------------------
class Projectsubmission(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]

    student = models.ForeignKey(
        'UserRegistration',
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'student'},
        related_name='submissions',
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    technology_used = models.CharField(max_length=200)
    team_members = models.TextField(
        blank=True,
        null=True,
        help_text="Optional: List of team members separated by commas"
    )

    # track timestamps
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
    'UserRegistration',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'role': 'teacher'},
        related_name='reviewed_projects',
    )
    reviewed_by = models.ForeignKey(UserRegistration, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_projects')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    feedback = models.TextField(blank=True, null=True)  
    def __str__(self):
        return f"{self.title} by {self.student.full_name}"
    

# -------------------- SUBMISSION DEADLINE MODEL --------------------

class SubmissionDeadline(models.Model):
    deadline = models.DateField()
    teacher_deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Student Deadline: {self.deadline} | Teacher Deadline: {self.teacher_deadline or 'Not Set'}"