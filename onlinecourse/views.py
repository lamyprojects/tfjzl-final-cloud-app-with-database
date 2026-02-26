import logging

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import generic

# <HINT> Import any new Models here
from .models import (
    Course,
    Enrollment,
    Submission,
    Choice,
)


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
            logger.info("New user registration")

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")
        else:
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
        else:
            context['message'] = "Invalid username or password."
            return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    else:
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


# An example method to collect the selected choices from the exam form from the request object
def extract_answers(request):
    submitted_answers = []
    for key in request.POST:
        if key.startswith('choice'):
            value = request.POST[key]
            choice_id = int(value)
            submitted_answers.append(choice_id)
    return submitted_answers


# <HINT> Create a submit view to create an exam submission record for a course enrollment
def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    # Must be logged in to submit
    if not user.is_authenticated:
        return redirect('onlinecourse:login')

    # Get the enrollment for this user and course
    enrollment = Enrollment.objects.filter(user=user, course=course).first()
    if enrollment is None:
        # Not enrolled -> redirect back to course detail
        return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))

    # Create a submission record
    submission = Submission.objects.create(enrollment=enrollment)

    # Collect selected choices and add them to submission
    selected_choice_ids = extract_answers(request)
    for choice_id in selected_choice_ids:
        choice = Choice.objects.get(pk=choice_id)
        submission.choices.add(choice)

    return HttpResponseRedirect(
        reverse(viewname='onlinecourse:show_exam_result', args=(course.id, submission.id))
    )


# <HINT> Create an exam result view to check if learner passed exam and show results
def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(Submission, pk=submission_id)

    # All questions in this course
    questions = course.question_set.all()

    # Selected choices from this submission
    selected_choices = submission.choices.all()
    selected_choice_ids = [c.id for c in selected_choices]

    total_questions = questions.count()
    total_correct = 0

    # For each question determine correctness
    question_results = []
    for question in questions:
        correct_choices = question.choice_set.filter(is_correct=True)
        correct_choice_ids = [c.id for c in correct_choices]

        # Choices selected for this question
        selected_for_question = selected_choices.filter(question=question)
        selected_for_question_ids = [c.id for c in selected_for_question]

        # Correct if sets match exactly (selected all correct and no wrong)
        is_correct = set(selected_for_question_ids) == set(correct_choice_ids)

        if is_correct:
            total_correct += 1

        question_results.append({
            "question": question,
            "is_correct": is_correct,
        })

    score = 0
    if total_questions > 0:
        score = int((total_correct / total_questions) * 100)

    context = {
        "course": course,
        "submission": submission,
        "selected_choice_ids": selected_choice_ids,
        "question_results": question_results,
        "score": score,
        "total_correct": total_correct,
        "total_questions": total_questions,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)