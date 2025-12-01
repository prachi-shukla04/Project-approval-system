from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register_page, name='register_page'),
    path('login/', views.login_page, name='login_page'),
    path('logout/', views.logout_page, name='logout'),
    path('index/', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('profile/', views.profile_page, name='profile'),

      
   


  # dashboard paths + student project actions

    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/submit_project/', views.submit_project, name='submit_project'),
    path('student/edit_project/<int:project_id>/', views.edit_project, name='update_project'),
    path('student/delete_project/<int:project_id>/', views.delete_project, name='delete_project'),
    path('check_project_status/', views.check_project_status, name='check_project_status'),


#teacher dashboard + project approval
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/approve_project/<int:project_id>/', views.approve_project, name='approve_project'),
    path('teacher/reject_project/<int:project_id>/', views.reject_project, name='reject_project'),
    path('teacher/feedback/', views.handle_project_feedback, name='handle_project_feedback'),


    
     # Admin dashboard + verification
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('approve_user/<int:user_id>/', views.approve_user, name='approve_user'),
    path('reject_user/<int:user_id>/', views.reject_user, name='reject_user'),
    path('assign-teacher/<int:student_id>/', views.assign_teacher, name='assign_teacher'),
    path('admin_dashboard/manage_users/', views.manage_users, name='manage_users'),
    path('admin_dashboard/delete_user/<int:user_id>/', views.delete_user, name='delete_user'),
    path('set_deadline/', views.set_submission_deadline, name='set_deadline'),
    path('admin_dashboard/restore_user/<int:user_id>/', views.restore_user, name='restore_user'),

        
]
