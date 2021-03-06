import simplejson

from django.views.generic import TemplateView
from django.contrib.auth.models import User
from django.views.generic import DetailView, View
from django.db.models import Q
from django.contrib.gis.measure import D
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse
from django.utils.translation import ugettext as _
from django.core.urlresolvers import reverse

from sesql.shortquery import shortquery

from leaflet_storage.models import Map
from leaflet_storage.forms import DEFAULT_CENTER


class PaginatorMixin(object):
    per_page = 5

    def paginate(self, qs):
        paginator = Paginator(qs, self.per_page)
        page = self.request.GET.get('p')
        try:
            qs = paginator.page(page)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page.
            qs = paginator.page(1)
        except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
            qs = paginator.page(paginator.num_pages)
        return qs


class Home(TemplateView, PaginatorMixin):
    template_name = "umap/home.html"
    list_template_name = "leaflet_storage/map_list.html"

    def get_context_data(self, **kwargs):
        qs = Map.public.filter(center__distance_gt=(DEFAULT_CENTER, D(km=1)))
        demo_map = None
        if hasattr(settings, "UMAP_DEMO_PK"):
            try:
                demo_map = Map.public.get(pk=settings.UMAP_DEMO_PK)
            except Map.DoesNotExist:
                pass
            else:
                qs = qs.exclude(id=demo_map.pk)
        showcase_map = None
        if hasattr(settings, "UMAP_SHOWCASE_PK"):
            try:
                showcase_map = Map.public.get(pk=settings.UMAP_SHOWCASE_PK)
            except Map.DoesNotExist:
                pass
            else:
                qs = qs.exclude(id=showcase_map.pk)
        maps = qs.order_by('-modified_at')[:50]
        maps = self.paginate(maps)

        return {
            "maps": maps,
            "demo_map": demo_map,
            "showcase_map": showcase_map,
            "DEMO_SITE": settings.UMAP_DEMO_SITE
        }

    def get_template_names(self):
        """
        Dispatch template according to the kind of request: ajax or normal.
        """
        if self.request.is_ajax():
            return [self.list_template_name]
        else:
            return [self.template_name]

home = Home.as_view()


class About(Home):

    template_name = "umap/about.html"

about = About.as_view()


class UserMaps(DetailView, PaginatorMixin):
    model = User
    slug_url_kwarg = 'username'
    slug_field = 'username'
    list_template_name = "leaflet_storage/map_list.html"
    context_object_name = "current_user"

    def get_context_data(self, **kwargs):
        manager = Map.objects if self.request.user == self.object else Map.public
        maps = manager.filter(Q(owner=self.object) | Q(editors=self.object)).distinct().order_by('-modified_at')[:30]
        maps = self.paginate(maps)
        kwargs.update({
            "maps": maps
        })
        return super(UserMaps, self).get_context_data(**kwargs)

    def get_template_names(self):
        """
        Dispatch template according to the kind of request: ajax or normal.
        """
        if self.request.is_ajax():
            return [self.list_template_name]
        else:
            return super(UserMaps, self).get_template_names()

user_maps = UserMaps.as_view()


class Search(TemplateView, PaginatorMixin):
    template_name = "umap/search.html"
    list_template_name = "leaflet_storage/map_list.html"

    def get_context_data(self, **kwargs):
        q = self.request.GET.get('q')
        maps = []
        if q:
            maps = shortquery(Q(classname='Map') & Q(fulltext__containswords=q))
            maps = self.paginate(maps)
        kwargs.update({
            'maps': maps,
            'q': q
        })
        return kwargs

    def get_template_names(self):
        """
        Dispatch template according to the kind of request: ajax or normal.
        """
        if self.request.is_ajax():
            return [self.list_template_name]
        else:
            return super(Search, self).get_template_names()

search = Search.as_view()


class MapsShowCase(View):

    def get(*args, **kargs):
        maps = Map.public.filter(center__distance_gt=(DEFAULT_CENTER, D(km=1))).order_by('-modified_at')[:2000]

        def make(m):
            description = m.description or ""
            if m.owner:
                description = u"{description}\n{by} [[{url}|{name}]]".format(
                    description=description,
                    by=_("by"),
                    url=reverse('user_maps', kwargs={"username": m.owner.username}),
                    name=m.owner,
                )
            description = u"{}\n[[{}|{}]]".format(description, m.get_absolute_url(), _("View the map"))
            geometry = m.settings['geometry'] if "geometry" in m.settings else simplejson.loads(m.center.geojson)
            return {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "name": m.name,
                    "description": description
                }
            }

        geojson = {
            "type": "FeatureCollection",
            "features": [make(m) for m in maps]
        }
        return HttpResponse(simplejson.dumps(geojson))

showcase = MapsShowCase.as_view()
