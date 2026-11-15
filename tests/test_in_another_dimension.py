"""Article #21: supplied Unicode, whitespace, metadata and preservation."""
from html import unescape
import json
import re
import subprocess
import unittest

from tools import generate_publication as g
from tools.search_index import SearchText


TEXT = {
    "ru": '''Некий особо одаренный господин заявил по прочтении "Часов Господа Бога": там ничего нет о том, почему мы не можем увидеть фотон от сверхсветового объекта.

Сначала я растерялась, поскольку, собственно, там нет... ничего другого.

Но потом вспомнила, что восторгов от почтеннейшей публики по поводу раскрытия тайны космических невидимок получила не то, чтобы в избытке, и решилась на еще одну попытку понять логику особо одаренных.

Занятие не из легких. Потому что, как заметил кто-то наблюдательный,

пытаясь думать за другого, мы часто переоцениваем соперника в силу его непредсказуемой и невообразимой для нас тупости.

К счастью, на этот раз ничего невообразимого не произошло.

Я без особого труда представила себе, что заставило моего оппонента сделать свое сногсшибательное заявление: он просто-напросто не понимает сути мысленного эксперимента.

Эмпирикам свойственно иметь дело с конкретными, осязаемыми вещами и делать конкретные, осязаемые выводы из манипуляций с ними.

В то время, как принципы мысленного эксперимента априори основываются на некотором произвольном допущении.

Очевидно, неприступность моего читателя спровоцирована тем, что и фотоны рассматриваемой вспышки-события, и гипотетический, обладающий сверхсветовой скоростью Белый Всадник - главный герой эссе, якобы начинали свое движение в один и тот же момент времени из одной и той же точки пространства.

Что, без сомнения, абсолютно невозможно в реальности. Хотя бы потому, что способные к сверхсветовым скоростям (антиматериальные) объекты всегда имеют координаты, соответствующие зеркальному отражению координат своих антиподов - материальных небесных тел (правило спт -симметрии), иначе, паче чаяния встретившись, антиподы незамедлительно аннигилировали бы между собой.

Но в том-то и дело, что совершенно невозможное в реальности - насущный хлеб мысленного эксперимента.

В том-то и дело, что в мысленном эксперименте для выявления некоего реального принципа рассматривается ситуация, от действительности несколько отличная.

Поэтому я не стала дополнительно оговаривать нюансы, сознательно упрощая. Как говорится, "розумному досыть".

И вот этот момент, по-видимому, оказался не по зубам моему "каменному гостю".

Он посчитал, что коль скоро фотоны находились изначально там же, где и сверхсветовой объект, то, отразившись от него, они обеспечат наблюдаемость означенного объекта.

На самом же деле, сверхсветовой объект находится, скорее, на одной "стартовой черте" с фотонами (на одинаковом с ними расстоянии от досветового наблюдателя), но отнюдь не в общем с ними пункте. На это ненавязчиво указывает частица "бы", сослагательное наклонение, примененное мною при упоминании о соревнующихся с ГГ фотонах.

А осуществленный мысленный эксперимент как раз и объясняет, почему они никогда не могут сойтись в одной и той же точке пространства-времени.

Происходит это потому, что в каждый данный момент мы видим исключительно фотоны событий, которые произошли n лет(часов, минут) назад на расстоянии в те же n световых лет(часов, минут). Именно эти фотоны достигают глаза наблюдателя.

Именно это и есть НАШЕ ИЗМЕРЕНИЕ, НАШЕ ПРОСТРАНСТВО-ВРЕМЯ. Оно "РАЗМЕЧЕНО" скоростью фотона.

Фотоны, которым не хватило времени добраться до наблюдателя, или те, что имели больше времени, чем необходимо, наблюдателем не регистрируются, а значит - не видны и объекты, находящиеся в рассматриваемый момент в соответствующих пунктах пространства-времени.

Поскольку n - любое положительное число натурального ряда, то объекты досветовые в какой-то момент времени неизбежно станут источниками отраженного света и будут обнаружены наблюдателем.

Другое дело, когда скорость света превышена. Объект, движущийся со сверхсветовой скоростью, невидим в принципе. Такие объекты - вечные невидимки. Откуда бы и когда бы ни началось их движение, как долго и в каком бы направлении оно ни продолжалось.

В силу своей запредельной скорости объекты из антивещества постоянно находятся в обратном конусе света - В ОТРИЦАТЕЛЬНОМ ПРОСТРАНСТВЕ-ВРЕМЕНИ, В ДРУГОМ ИЗМЕРЕНИИ, наблюдателю досветовому, продукту материального мира, для созерцания недоступном.

И эту простую истину необходимо усвоить каждому, кто хочет ориентироваться в сложных построениях современной физики.''',
    "en": '''A particularly gifted gentleman, after reading “The Clocks of the Lord God,” declared that it said nothing about why we cannot see a photon from a superluminal object.

At first I was bewildered, since, in fact, it contains... nothing else.

But then I remembered that I had hardly received an abundance of enthusiasm from the esteemed public over my revelation of the secret of cosmic invisibles, and decided to make one more attempt to understand the logic of the particularly gifted.

No easy undertaking. Because, as someone observant once remarked,

when trying to think for someone else, we often overestimate our opponent, owing to a stupidity on their part that is unpredictable and unimaginable to us.

Fortunately, this time nothing unimaginable occurred.

I had little difficulty imagining what prompted my opponent to make his staggering declaration: he simply does not understand the essence of a thought experiment.

Empiricists tend to deal with concrete, tangible things and draw concrete, tangible conclusions from manipulating them.

Whereas the principles of a thought experiment are based, a priori, on a certain arbitrary assumption.

Evidently, what made my reader so impervious was the fact that both the photons of the flash-event under consideration and the hypothetical White Rider, capable of superluminal speed and the main character of the essay, supposedly began moving at the same moment in time from the same point in space.

Which, without a doubt, is absolutely impossible in reality. If only because objects capable of superluminal speeds (antimaterial objects) always have coordinates corresponding to the mirror reflection of the coordinates of their antipodes—material celestial bodies (the rule of CPT symmetry); otherwise, should the antipodes unexpectedly encounter one another, they would immediately annihilate each other.

But that is precisely the point: what is utterly impossible in reality is the very bread and butter of a thought experiment.

That is precisely the point: in a thought experiment, a situation somewhat different from reality is considered in order to reveal a certain real principle.

That is why I did not additionally spell out the nuances, deliberately simplifying matters. As the saying goes, “розумному досыть” (“enough for the wise”).

And this point, apparently, proved too much for my “stone guest” to grasp.

He reasoned that since the photons were initially in the same place as the superluminal object, they would reflect off it and make that object observable.

In reality, however, the superluminal object is, rather, at the same “starting line” as the photons (at the same distance from the subluminal observer), but by no means at the same location as them. This is subtly indicated by the particle “бы”, the conditional mood I used when mentioning the photons supposedly competing with the protagonist.

And the thought experiment itself explains precisely why they can never meet at the same point in spacetime.

This happens because, at any given moment, we see exclusively the photons of events that occurred n years (hours, minutes) ago, at a distance of the same n light-years (light-hours, light-minutes). It is these photons that reach the observer's eye.

This is precisely OUR DIMENSION, OUR SPACETIME. It is “MARKED OUT” by the speed of the photon.

Photons that have not had enough time to reach the observer, or those that have had more time than necessary, are not registered by the observer; therefore, objects located at the corresponding points in spacetime at the moment under consideration are also invisible.

Since n is any positive natural number, subluminal objects will inevitably, at some point, become sources of reflected light and be detected by the observer.

It is another matter when the speed of light is exceeded. An object moving at superluminal speed is invisible in principle. Such objects are eternally invisible. Regardless of where or when their motion began, how long it continues, or in what direction.

By virtue of their extraordinary speed, objects made of antimatter are constantly situated in the reverse light cone—IN NEGATIVE SPACETIME, IN ANOTHER DIMENSION, inaccessible to the gaze of a subluminal observer, a product of the material world.

And this simple truth must be understood by everyone who wishes to find their way through the complex constructions of modern physics.''',
}


class InAnotherDimensionTests(unittest.TestCase):
    def test_exact_text_metadata_and_discovery(self):
        catalog = g.load_json(g.ROOT / "publication/catalog.json")
        articles = [w["path"] for w in catalog["works"]["items"] if w["type"] == "article"]
        self.assertEqual(articles[-4:-2], ["/articles/epatazhka/", "/articles/in-another-dimension/"])
        self.assertEqual(len(articles), 41)
        for language, prefix, title in (("ru", "", "В ДРУГОМ ИЗМЕРЕНИИ"), ("en", "en/", "In Another Dimension")):
            route = "/" + prefix + "articles/in-another-dimension/"
            source = (g.ROOT / route.lstrip("/") / "index.html").read_text(encoding="utf-8")
            body = re.search(r'<div id="article-text">(.*?)</div>', source, re.S)[1]
            paragraphs = re.findall(r'<p style="white-space: pre-wrap;">(.*?)</p>', body, re.S)
            self.assertEqual(len(paragraphs), 25)
            self.assertEqual("\n\n".join(unescape(p) for p in paragraphs), TEXT[language])
            self.assertIn('<h1><strong>' + title + '</strong></h1>', source)
            label = "Оригинал на русском: " if language == "ru" else "Russian original: "
            self.assertEqual(re.findall(r'<div class="note">.*?</div>', source), [
                '<div class="note">' + label + '<a href="https://samlib.ru/b/berezina_e_l/dlheujvbpvthtybb.shtml">Samlib</a>.</div>'])
            self.assertIn('class="back" href="/' + prefix + 'articles/page-4/"', source)
            page = g.PageHTML(source)
            metadata = {a.get("name", a.get("property")): a.get("content") for a in page.matching("meta")}
            self.assertEqual(metadata["og:title"], title)
            self.assertEqual(metadata["twitter:title"], title)
            self.assertTrue(metadata["description"])
            self.assertEqual(metadata["og:description"], metadata["description"])
            self.assertEqual(metadata["twitter:description"], metadata["description"])
            self.assertEqual(source.count(g.BEACON_URL), 1)
            for lang, start in (("ru", ""), ("en", "en/")):
                target = "/" + start + "articles/in-another-dimension/"
                self.assertIn({"rel": "alternate", "hreflang": lang, "href": g.SITE + target}, page.matching("link"))
                switch = [a for a in page.matching("a") if a.get("hreflang") == lang]
                self.assertEqual(len(switch), 1)
                self.assertEqual(switch[0]["href"], target)
                self.assertEqual(switch[0].get("aria-current"), "page" if lang == language else None)
            index = "assets/search-index" + ("-en" if language == "en" else "") + ".json"
            entry = next(p for p in json.loads((g.ROOT / index).read_bytes())["pages"] if p["url"] == g.SITE + route)
            self.assertEqual(entry["text"], SearchText("<main>" + body + "</main>").text + " " + label + "Samlib.")

    def test_previous_publications_and_records_are_unchanged(self):
        baseline = "524a7859c84be9e861f45d55e25054cd44ec2f8b"

        def old(name):
            return subprocess.check_output(["git", "show", baseline + ":" + name], cwd=g.ROOT)

        def is_new(path):
            return path.endswith(("/articles/in-another-dimension/", "/articles/the-path-of-progress/", "/articles/negative-time/", "/articles/no-problems/", "/articles/page-5/"))

        catalog = g.load_json(g.ROOT / "publication/catalog.json")
        previous = json.loads(old("publication/catalog.json"))
        for key, field in (("pages", "path"), ("alternate_groups", "ru")):
            catalog[key] = [p for p in catalog[key] if not is_new(p[field])]
        catalog["works"]["items"] = [w for w in catalog["works"]["items"] if not is_new(w["path"])]
        self.assertEqual(catalog, previous)
        authored = [p["path"].lstrip("/") + "index.html" for p in previous["pages"]
                    if not g.is_article_listing(p["path"]) and p["path"] not in ("/works/", "/en/works/")]
        for name in authored:
            expected = old(name).decode().replace("\r\n", "\n")
            if name.endswith("articles/piece-of-cybernetics/index.html"):
                prefix = "/en/" if name.startswith("en/") else "/"
                expected = expected.replace('class="back" href="' + prefix + 'articles/page-3/"',
                                            'class="back" href="' + prefix + 'articles/page-4/"')
            self.assertEqual((g.ROOT / name).read_text(encoding="utf8"), expected, name)
        for name, key in (("api/agent-feed/v1.json", "entries"), ("assets/search-index.json", "pages"),
                          ("assets/search-index-en.json", "pages")):
            current = json.loads((g.ROOT / name).read_bytes())
            current[key] = [p for p in current[key] if not is_new(p.get("url", p.get("id", "")))]
            self.assertEqual(current, json.loads(old(name)), name)
        current_catalog = g.load_json(g.ROOT / "publication/catalog.json")
        for name, expected in g.render_article_pages(g.ROOT, g.article_catalog(current_catalog)).items():
            self.assertEqual((g.ROOT / name).read_bytes(), expected, name)
        for name, expected in g.render_article_pages(g.ROOT, g.article_catalog(catalog)).items():
            self.assertEqual(expected, old(name), name)
        for language in ("ru", "en"):
            counts = [(g.ROOT / (g.article_route(language, number).lstrip("/") + "index.html"))
                      .read_text(encoding="utf8").count('<div class="item">')
                      for number in range(1, 6)]
            self.assertEqual(counts, [10, 10, 10, 10, 1])


if __name__ == "__main__":
    unittest.main()
