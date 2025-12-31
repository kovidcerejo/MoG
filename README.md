# Meals of Gratitude
#### Video Demo: https://youtu.be/ecTDfcoCY5o
## Website Description
This website is meant to help me run an organization at my school that is titled Meals of Gratitude. The program allows parent volunteers to cook meals or send gift cards to teachers at my school in order to show their appreciation. The website I built streamlines the process for the volunteers, teachers, and also me (the coordinator). The website consolidates the processes of volunteers sharing recipes and signing up to give meals or gift cards, teachers selecting meals/gift cards to receive, and me scheduling all of the dropoffs and sending reminder emails to both teachers and volunteers. In addition, the website has extra features on top of those to simplify the process and make it easier.

## Website Structure
The website is structured into three main parts: one for volunteers, one for teachers, and one for the admin (me). Each part needs a different code to access, and once entered, the browser remembers your credentials for your next visit.
### Admin
From the main website, to get to the admin page, you have to add "/admin" to the url in the search bar, since there is no direct link from the website to the admin page. From the admin portal, you can add/edit volunteers, set volunteer/teacher portal passwords, view/edit deadlines for each month (more on this later), view rankings of recipes and volunteers, send reminder emails out for the month, and push the rewards to the teachers. You can also add/edit reward signups past the deadline, overriding the deadline in special cases, and also edit or delete volunteer recipes.
### Volunteers
From the main website, you can click on the "volunteers" button to get to the volunteer portal, making sure you enter the correct volunteer code. From there, you can view the signups from other volunteers for the month, view and add to the collection of recipes, and sign up to deliver a meal or gift card. Volunteers also have the ability to edit or delete their signup once submitted, given the volunteer submission period is still ongoing.
### Teachers
From the homepage, teachers can click on the "teachers" button and enter the code in order to gain access to the teacher portal. From there, if the teacher sign-up period is ongoing, they may sign up to receive a gift card or meal. To do so, they simply type their name and email next to the meal/gc they would like to receive. They can also click on recipe names to view the recipe page with ingredients, instructions, and images.
## Note on Deadlines
Part of the admin functionality mentioned above is creating the deadlines for each month. These deadlines, created by the admin each month, ensure volunteers can only sign up to cook meals or send gift cards during the period specified by the admin (usually the first week of the month). Outside of that period, the volunteer portal changes and doesn't allow modifications to be made. The deadlines also ensure teachers can only sign up for meals or gift cards after the volunteers sign up in the first place, so the teacher deadlines are usually around the second week of the month. Similarly to the volunteer portal, outside of the time period specified by teacher deadlines, the teacher portal appears empty and doesn't allow teachers to do much. Finally, the last set of deadlines are for dropoff, which specifies when volunteers can go to school to give their meals/gift cards to the teacher who selected them. Some of the deadlines, like "Volunteer Start" and "Teacher Start" are dynamically created when the month's dates are set by the admin. Some deadlines must manually be entered by the admin.
## Project Files
The static directory contains an image folder where all the recipe images uploaded by volunteers go. It also contains the CSS stylesheet and favicon image that goes in the tab preview. The templates folder contains all of the jinja files directed to in the main app.py file. The app.py file contains almost all of the main code and website logic, and uses the Flask framework.
## SQL Database Structure
The backbone of the website's inner workings is the "meals.db" file, which is created and modified using SqLite3. There are 9 tables in the database, each with a different purpose. There is a table for deadlines, passwords (encrypted), teachers, volunteers, recipes, meals, gift cards, teacher codes, and volunteer keys. The teachers and volunteers tables have ids that are referenced as foreign keys in the meals, recipes, and gift card tables.  




