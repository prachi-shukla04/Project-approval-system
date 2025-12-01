from django import forms
from .models import Projectsubmission, Project, UserRegistration, SubmissionDeadline

# 🧑‍🎓 Form for students to submit their project
class ProjectSubmissionForm(forms.ModelForm):
    class Meta:
        model = Projectsubmission
        fields = ['title', 'description', 'technology_used', 'team_members']

        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'Enter your project title (max 100 words)',
                'class': 'input-box',
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Describe your project idea clearly (max 1000 words)',
                'rows': 5,
                'class': 'input-box',
            }),
            'technology_used': forms.TextInput(attrs={
                'placeholder': 'Technologies used (e.g. Python, Django, HTML, CSS)',
                'class': 'input-box',
            }),
            'team_members': forms.TextInput(attrs={
                'placeholder': 'Team members, separated by commas (optional)',
                'class': 'input-box',
            }),
        }

    def clean_title(self):
        title = self.cleaned_data['title']
        if len(title.split()) > 100:
            raise forms.ValidationError("Title cannot exceed 100 words.")
        return title

    def clean_description(self):
        description = self.cleaned_data['description']
        if len(description.split()) > 1000:
            raise forms.ValidationError("Description cannot exceed 1000 words.")
        return description


# 🧾 Form for admin/teachers to manage projects
class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['title', 'description', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


# 👤 Form for editing user profile
class EditProfileForm(forms.ModelForm):
    class Meta:
        model = UserRegistration
        fields = ['full_name', 'email', 'password']
        widgets = {
            'password': forms.PasswordInput(attrs={'placeholder': 'Enter new password if you want to change'}),
        }


# 🗓️ Form for setting submission deadline
class SubmissionDeadlineForm(forms.ModelForm):
    class Meta:
        model = SubmissionDeadline
        fields = ['deadline','teacher_deadline']
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'teacher_deadline': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
