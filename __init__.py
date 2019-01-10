"""
skill good manners

Copyright (C) 2018 JarbasAI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
 copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.

"""

from mycroft import MycroftSkill
from datetime import timedelta, datetime
from insults import Insults
from ai_demos.cornell import politeness


class GoodMannersEnforcerSkill(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)
        if "simple" not in self.settings:
            # if False use slower more accurate machine learning techniques
            self.settings["simple"] = True
        if "insult_threshold" not in self.settings:
            self.settings["insult_threshold"] = 0.65  # min insult rating
        if "polite_threshold" not in self.settings:
            self.settings["polite_threshold"] = 4  # times for comeback
        if "polite_timeout" not in self.settings:
            self.settings["polite_timeout"] = 10  # minutes
        self.model_loaded = False
        self.comebacks = []
        self.foul_words = []
        self.polite_counter = 0
        self.last_timestamp = datetime.now()
        self.settings.set_changed_callback(self.maybe_load_insult_model)

    @property
    def simple(self):
        if not self.lang.lower().startswith("en"):
            return True
        return self.settings["simple"]

    def initialize(self):
        self.maybe_load_insult_model()
        self.add_event("recognizer_loop:utterance", self.ensure_converse)
        self.add_event("mycroft.skill.handler.complete", self.handle_output)
        self.ensure_converse()

    def maybe_load_insult_model(self):
        if not self.model_loaded and not self.simple:
            # load insult classifier
            Insults.load_model()
            self.model_loaded = True

    def contains_foul_language(self, utterance):
        contains = False
        if self.simple:
            return self.match_voc_file(utterance, "foul_language")
        else:
            foul_words, _ = Insults.foul_language([utterance], context=False)
            if len(foul_words):
                contains = True
        return contains, foul_words

    def match_voc_file(self, utterance, voc_file):
        if self.voc_match(utterance, voc_file):
            foul_words = [w for w in
                          self.voc_match_cache[self.lang + voc_file]
                          if w in utterance]
            return True, foul_words
        return False, []

    def is_insult(self, utterance):
        if not self.simple:
            rating = Insults.rate_comment(utterance)
            if rating >= self.settings["insult_threshold"]:
                return True
        return False

    def is_polite(self, utterance):
        if self.simple:
            return self.voc_match(utterance, "polite_words")
        else:
            analysis = politeness(utterance)
            if analysis["label"] == "polite":
                return True
        return False

    def handle_output(self, message):
        if "polite" in self.comebacks:
            self.speak_dialog("was_polite")
        if "insult" in self.comebacks:
            self.speak_dialog("said_insult")
        if "foul" in self.comebacks:
            self.speak_dialog("said_foul_language",
                              {"foul_words": " and ".join(self.foul_words)})

    def ensure_converse(self, message=None):
        # ensure converse is called
        # NOTE possible race condition
        # TODO update once PR#1468 is merged
        # https://github.com/MycroftAI/mycroft-core/pull/1468
        self.make_active()

    def handle_reset_event(self, message=None):
        self.ensure_converse()
        if self.polite_counter < self.settings["polite_threshold"]:
            self.comebacks = []
        # reset counter if timeout was reached
        elif datetime.now() - self.last_timestamp > \
                timedelta(minutes=self.settings["polite_timeout"]):
            self.polite_counter = 0
            self.comebacks = []
        # check for timeout again in 1 minute
        self.schedule_event(self.handle_reset_event,
                            datetime.now() + timedelta(minutes=1),
                            name='politeness_timeout')

    def converse(self, utterances, lang="en-us"):
        # pre-process utterance
        utterance = utterances[0]
        self.comebacks = []
        insult = self.is_insult(utterance)
        foul, self.foul_words = self.contains_foul_language(utterance)
        if not insult and not foul:
            if self.is_polite(utterance):
                self.comebacks.append("polite")
                # start monitoring for timeout
                self.last_timestamp = datetime.now()
                self.schedule_event(self.handle_reset_event,
                                    datetime.now() + timedelta(minutes=1),
                                    name='politeness_timeout')
        else:
            self.polite_counter = 0
            if insult:
                self.comebacks.append("insult")
            if foul:
                self.comebacks.append("foul")
        self.ensure_converse()
        return False


def create_skill():
    return GoodMannersEnforcerSkill()
