# Redis Cache Key Reference

## Overview
This document describes all Redis cache keys used in the backend, including their structure, stored data, and invalidation rules. Proper cache invalidation is **critical** for ensuring up-to-date data is served to users. Whenever related database data changes, the corresponding cache keys **must** be deleted.

---

## Table of Contents
1. [Student Data Keys](#1-student-data-keys)
2. [Subject Data Keys](#2-subject-data-keys)
3. [Clerk Data Keys](#3-clerk-data-keys)
4. [Teacher Data Keys](#4-teacher-data-keys)
5. [Invalidation Guidelines](#invalidation-guidelines)

---

## 1. Student Data Keys

### a) Student List by Department/Program/Semester
**student:{program}:{department}:{semester}:{batch_year}**  
- **Stores:** List of all students in a specific department, program, and semester.  
- **Use case:** Used by teachers to search for students when manually adding students during attendance.  
- **Invalidate when:**  
  - A student is added or removed from this group.  
  - A student’s department, program, or semester changes.  

### b) Individual Student Profile
**student:{email}**  
- **Stores:** Personal data for a single student.  
- **Use case:** Used to retrieve data of a single student for their profile tab.  
- **Invalidate when:**  
  - Student updates personal information (name, contact info, profile image).  
  - Student account is deleted.  

---

## 2. Subject Data Keys

### c) Subject List by Program/Department/Semester
**subjects:{program}:{department}:{semester}**  
- **Stores:** Names and codes for all subjects in a specific semester, department, and program.  
- **Use case:** Used by students to get basic details of the subject, including name, code, and assigned teacher.  
- **Invalidate when:**  
  - A subject is added or removed from this set.  
  - A subject’s name or code changes.  

### f) Subject List for Program
**subjects:{program}**  
- **Stores:** All subjects for a program across all semesters (1, 2, 3).  
- **Use case:** Used to get complete details of subjects, including attendance percentage and other data (attendance, defaulter lists, etc.).  
- **Note:** For now, data can match with **subjects:{program}:{department}:{semester}**.  
- **Invalidate when:**  
  - Any subject in the program changes.  
  - Subject details change.  
  - A subject is added or removed from the program.  
  - Attendance is updated.  

### j) Detailed Subject Data for Specific Subject
**subject:{subject_id}**  
- **Stores:** Detailed data for one subject within a program (marks, attendance, schedule).  
- **Use case:** Used by clerks to see a full detailed view of a specific subject, including analytics.  
- **Invalidate when:**  
  - Data for this subject changes.  

---

## 3. Clerk Data Keys

### d) Clerks by Department
**clerks:{department}**  
- **Stores:** All clerks in a department.  
- **Invalidate when:**  
  - A clerk is added or removed from the department.  
  - A clerk’s details change.  

### e) Clerk by Email
**clerk:{email_id}**  
- **Stores:** Data for a single clerk.  
- **Invalidate when:**  
  - A clerk’s personal data changes.  
  - The clerk is removed.  

---

## 4. Teacher Data Keys

### g) Teachers by Department
**teachers:{department}**  
- **Stores:** All teachers associated with a department.  
- **Use case:** Used by clerks to retrieve teachers for a department.  
- **Invalidate when:**  
  - A teacher is added or removed from the department.  
  - A teacher’s department changes.  

### h) Teacher by ID
**teacher:{teacher_id}**  
- **Stores:** Detailed data for a specific teacher, including teaching history and student attendance percentages.  
- **Use case:** Used by clerks to view detailed statistics for a teacher, including daily, weekly, and full-term metrics.  
- **Note:** Currently matches data with **teacher:{email}**, but will be separated in the future.  
- **Invalidate when:**  
  - A teacher’s profile or teaching data changes.  

### i) Teacher by Email
**teacher:{email}**  
- **Stores:** Detailed data for a specific teacher’s profile.  
- **Invalidate when:**  
  - A teacher’s profile or teaching data changes.  

---

## Invalidation Guidelines
When making updates to the database:  
1. **Identify related keys** from this document.  
2. **Delete them from Redis** to force regeneration with updated data.  
3. **If unsure**, delete both list keys (e.g., **students:{...}**) and detailed keys (e.g., **student:{email}**) to avoid serving stale data.
