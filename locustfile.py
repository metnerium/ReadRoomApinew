from locust import HttpUser, task, between, TaskSet
from random import choice, randint
import json
import logging


class UserBehavior(TaskSet):
    def on_start(self):
        # Login to get access token
        self.token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzNjU2MzQ5MTkiLCJleHAiOjc3Mjk4MjczMzN9.HFquMDY8PtYkLOE6I3to8t76LpTZmApCh0YwIKQa1D4'

        self.headers = {'Authorization': f'Bearer {self.token}'}
        # Initialize story cache
        self.stories = []
        self.user_id = None
        # Get user info and stories
        self.get_user_info()
        self.get_user_stories()


    def get_user_info(self):
        response = self.client.get("/users/me", headers=self.headers)
        if response.status_code == 200:
            user_data = response.json()
            self.user_id = user_data["id"]

    def get_user_stories(self):
        if self.user_id:
            response = self.client.get(f"/usercontent/users/{self.user_id}/stories", headers=self.headers)
            if response.status_code == 200:
                self.stories = response.json()

    @task(3)
    def view_stories(self):
        # List stories with different sorting and filtering
        sorts = ["rating"]
        genres = ["fiction", "non-fiction", "mystery", "romance",
                  "science_fiction", "fantasy", "horror", "poetry",
                  "thoughts", "ideas"]

        sort_by = choice(sorts)
        genre = choice(genres)
        response = self.client.get(
            f"/stories/?sort_by={sort_by}&genre={genre}&skip=0&limit=20",
            headers=self.headers
        )
        if response.status_code == 200:
            stories_data = response.json()
            if stories_data["stories"]:
                self.stories.extend([story for story in stories_data["stories"]
                                     if story["id"] not in [s["id"] for s in self.stories]])

    # @task(1)
    # def create_story(self):
    #     genres = ["fiction", "non-fiction", "mystery", "romance",
    #               "science_fiction", "fantasy", "horror", "poetry",
    #               "thoughts", "ideas"]
    #     response = self.client.post("/stories/",
    #                                 headers=self.headers,
    #                                 json={
    #                                     "title": f"Test Story {randint(1, 1000)}",
    #                                     "summary": "A test story for load testing",
    #                                     "genre": choice(genres),
    #                                     "cover_image_url": None
    #                                 }
    #                                 )
    #     if response.status_code == 200:
    #         story_data = response.json()
    #         self.stories.append(story_data)
    #         self.create_chapter(story_data["id"])
    #
    # def create_chapter(self, story_id):
    #     self.client.post("/chapters/",
    #                      headers=self.headers,
    #                      json={
    #                          "title": f"Chapter {randint(1, 10)}",
    #                          "content": "This is a test chapter content",
    #                          "story_id": story_id,
    #                          "chapter_number": 1
    #                      }
    #                      )
    #
    # @task(3)
    # def view_story_details(self):
    #     if self.stories:
    #         story = choice(self.stories)
    #         self.client.get(f"/stories/{story['id']}", headers=self.headers)
    #
    # @task(3)
    # def view_chapters(self):
    #     if self.stories:
    #         story = choice(self.stories)
    #         self.client.get(f"/chapters/story/{story['id']}", headers=self.headers)
    #
    # @task(1)
    # def view_authors(self):
    #     response = self.client.get("/users/authors", headers=self.headers)
    #     if response.status_code == 200:
    #         self.authors = response.json()
    #
    # @task(2)
    # def view_bookmarks(self):
    #     self.client.get("/users/bookmarks", headers=self.headers)


class WebsiteUser(HttpUser):
    tasks = [UserBehavior]
    wait_time = between(1, 5)  # Random wait time between tasks
    host = "https://api-metnerium.ru"  # Replace with your API host

    def on_start(self):
        logging.info("User started")