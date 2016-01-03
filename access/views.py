from django.shortcuts import render
from django.http.response import HttpResponse, JsonResponse, Http404
from django.utils import timezone
from django.utils import translation
from django.utils.module_loading import import_by_path
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.conf import settings
from access.config import ConfigParser, ConfigError
from grader.tasks import queue_length as qlength
import os
import copy


# Hold on to the latest configuration for several requests.
config = ConfigParser()


def index(request):
    '''
    Signals that the grader is ready and lists available courses.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    courses = config.courses()
    if request.is_ajax():
        return JsonResponse({
            "ready": True,
            "courses": _filter_fields(courses, ["key", "name"])
        })
    return render(request, 'access/ready.html', { "courses": courses })


def course(request, course_key):
    '''
    Signals that the course is ready to be graded and lists available exercises.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @type course_key: C{str}
    @param course_key: a key of the course
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    (course, exercises) = config.exercises(course_key)
    if course is None:
        raise Http404()
    if request.is_ajax():
        return JsonResponse({
            "ready": True,
            "course_name": course["name"],
            "exercises": _filter_fields(exercises, ["key", "title"]),
        })
    return render(request, 'access/course.html', {
        'course': course,
        'exercises': exercises,
        'plus_config_url': request.build_absolute_uri(reverse(
            'access.views.aplus_json', args=[course['key']])),
    })


def exercise(request, course_key, exercise_key):
    '''
    Presents the exercise and accepts answers to it.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @type course_key: C{str}
    @param course_key: a key of the course
    @type exercise_key: C{str}
    @param exercise_key: a key of the exercise
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    post_url = request.GET.get('post_url', None)
    lang = request.GET.get('lang', None)

    # Fetch the corresponding exercise entry from the config.
    (course, exercise) = config.exercise_entry(course_key, exercise_key, lang=lang)
    if course is None or exercise is None:
        raise Http404()

    # Exercise language.
    if not lang:
        if "lang" in course:
            lang = course["lang"]
        else:
            lang = "en"
    translation.activate(lang)

    # Try to call the configured view.
    exview = None
    try:
        exview = import_by_path(exercise["view_type"])
    except ImproperlyConfigured as e:
        raise ConfigError("Invalid \"view_type\" in exercise configuration.", e)
    return exview(request, course, exercise, post_url)


def ajax_submit(request, course_key, exercise_key):
    '''
    Receives an AJAX submission for an exercise.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @type course_key: C{str}
    @param course_key: a key of the course
    @type exercise_key: C{str}
    @param exercise_key: a key of the exercise
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    return HttpResponse("bla")


def aplus_json(request, course_key):
    '''
    Delivers the configuration as JSON for A+.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @type course_key: C{str}
    @param course_key: a key of the course
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    course = config.course_entry(course_key)
    if course is None:
        raise Http404()
    data = _copy_fields(course, ["name", "description", "lang", "contact",
        "assistants", "start", "end", "categories",
        "numerate_ignoring_modules"])

    def children_recursion(parent):
        if not "children" in parent:
            return []
        result = []
        for o in [o for o in parent["children"] if "key" in o]:
            if "config" in o:
                _, exercise = config.exercise_entry(course["key"], o["key"])
                of = {
                    "title": exercise.get("title", ""),
                    "description": exercise.get("description", ""),
                    "url": request.build_absolute_uri(
                        reverse('access.views.exercise', args=[
                            course["key"], exercise["key"]
                        ])),
                }
            elif "static_content" in o:
                of = {
                    "url": request.build_absolute_uri(
                        '{}{}/{}'.format(settings.STATIC_URL,
                            course["key"], o["static_content"])),
                }
            else:
                of = {}
            of.update(o)
            of["children"] = children_recursion(o)
            result.append(_type_dict(of, course.get("exercise_types", {})))
        return result

    modules = []
    if "modules" in course:
        for m in course["modules"]:
            mf = _type_dict(m, course.get("module_types", {}))
            mf["children"] = children_recursion(m)
            modules.append(mf)
    data["modules"] = modules
    return JsonResponse(data)


def queue_length(request):
    '''
    Reports the current queue length.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    return HttpResponse(qlength())


def test_result(request):
    '''
    Accepts a result from a test submission.

    @type request: C{django.http.request.HttpRequest}
    @param request: a request to handle
    @rtype: C{django.http.response.HttpResponse}
    @return: a response
    '''
    file_path = os.path.join(settings.SUBMISSION_PATH, 'test-result')
    if request.method == 'POST':
        vals = request.POST.copy()
        vals['time'] = str(timezone.now())
        with open(file_path, 'w') as f:
            import json
            f.write(json.dumps(vals))
        return JsonResponse({ "success": True })
    result = None
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            result = f.read()
    return HttpResponse(result or 'No test result received yet.')


def _filter_fields(dict_list, pick_fields):
    '''
    Filters picked fields from a list of dictionaries.

    @type dict_list: C{list}
    @param dict_list: a list of dictionaries
    @type pick_fields: C{list}
    @param pick_fields: a list of field names
    @rtype: C{list}
    @return: a list of filtered dictionaries
    '''
    result = []
    for entry in dict_list:
        new_entry = {}
        for name in pick_fields:
            new_entry[name] = entry[name]
        result.append(new_entry)
    return result


def _copy_fields(dict_item, pick_fields):
    '''
    Copies picked fields from a dictionary.

    @type dict_item: C{dict}
    @param dict_item: a dictionary
    @type pick_fields: C{list}
    @param pick_fields: a list of field names
    @rtype: C{dict}
    @return: a dictionary of picked fields
    '''
    result = {}
    for name in pick_fields:
        if name in dict_item:
            result[name] = copy.deepcopy(dict_item[name])
    return result

def _type_dict(dict_item, dict_types):
    '''
    Extends dictionary with a type reference.

    @type dict_item: C{dict}
    @param dict_item: a dictionary
    @type dict_types: C{dict}
    @param dict_types: a dictionary of type dictionaries
    @rtype: C{dict}
    @return: an extended dictionary
    '''
    base = {}
    if "type" in dict_item and dict_item["type"] in dict_types:
        base = copy.deepcopy(dict_types[dict_item["type"]])
    base.update(dict_item)
    if "type" in base:
        del base["type"]
    return base
