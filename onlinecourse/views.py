from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
import logging

from .models import Course, Enrollment, Question, Choice, Submission

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except Exception:
            logger.error("New user")

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")
        context['message'] = "User already exists."
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        context['message'] = "Invalid username or password."
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    is_enrolled = False
    if user.id is not None:
        num_results = Enrollment.objects.filter(user=user, course=course).count()
        if num_results > 0:
            is_enrolled = True
    return is_enrolled


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)
    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))


def extract_answers(request):
    submitted_answers = []
    for key in request.POST:
        if key.startswith('choice'):
            value = request.POST[key]
            choice_id = int(value)
            submitted_answers.append(choice_id)
    return submitted_answers


def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if not user.is_authenticated:
        return redirect('onlinecourse:login')

    enrollment = get_object_or_404(Enrollment, user=user, course=course)

    # Create submission
    submission = Submission.objects.create(enrollment=enrollment)

    # Collect selected choices
    selected_choice_ids = extract_answers(request)
    for choice_id in selected_choice_ids:
        choice = get_object_or_404(Choice, pk=choice_id)
        submission.choices.add(choice)

    submission.save()

    return HttpResponseRedirect(
        reverse('onlinecourse:show_exam_result', args=(course.id, submission.id))
    )


def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(Submission, pk=submission_id)

    # all questions for this course
    questions = Question.objects.filter(course=course)

    # selected choices
    selected_choices = submission.choices.all()
    selected_choice_ids = set(selected_choices.values_list('id', flat=True))

    total_score = 0
    max_score = 0

    question_results = []
    for q in questions:
        max_score += q.grade

        correct_choice_ids = set(
            Choice.objects.filter(question=q, is_correct=True).values_list('id', flat=True)
        )
        selected_for_q = set(
            Choice.objects.filter(question=q, id__in=selected_choice_ids).values_list('id', flat=True)
        )

        # exact match -> full grade
        is_correct = (selected_for_q == correct_choice_ids) and len(correct_choice_ids) > 0
        if is_correct:
            total_score += q.grade

        question_results.append({
            "question": q,
            "selected_for_q": Choice.objects.filter(id__in=selected_for_q),
            "correct_for_q": Choice.objects.filter(id__in=correct_choice_ids),
            "is_correct": is_correct,
            "grade": q.grade
        })

    # pass rule (IBM lab obično 50%+)
    passed = False
    percentage = 0
    if max_score > 0:
        percentage = round((total_score / max_score) * 100, 2)
        passed = percentage >= 50

    context = {
        "course": course,
        "submission": submission,
        "total_score": total_score,
        "max_score": max_score,
        "percentage": percentage,
        "passed": passed,
        "question_results": question_results,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)