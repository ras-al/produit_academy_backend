from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from datetime import timedelta
import random

from rest_framework import generics, permissions, status, parsers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    UserSerializer, CourseRequestSerializer, StudyMaterialSerializer,
    MyTokenObtainPairSerializer, BranchSerializer, ChangePasswordSerializer,
    ResetPasswordSerializer, UserProfileSerializer
)
from .models import User, Branch, StudyMaterial, CourseRequest, Session

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class SignUpView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user.is_active = False
        user.save()

        # Student ID Generation
        student_id = f"PROD-{random.randint(1000, 9999)}"
        while User.objects.filter(student_id=student_id).exists():
            student_id = f"PROD-{random.randint(1000, 9999)}"
        user.student_id = student_id
        user.save()

        # Course Request Creation
        branch_id = request.data.get('branch')
        if branch_id:
            try:
                branch = Branch.objects.get(id=branch_id)
                CourseRequest.objects.create(student=user, branch=branch, status='Pending')
            except Branch.DoesNotExist:
                pass

        # OTP Logic
        otp = str(random.randint(1000, 9999))
        user.otp = otp
        user.otp_expiry = timezone.now() + timedelta(minutes=5)
        user.save()

        send_mail(
            'Your OTP for Produit Academy',
            f'Hi {user.username},\n\nYour One-Time Password (OTP) is: {otp}\nIt will expire in 5 minutes.',
            'from@produit.academy',
            [user.email],
            fail_silently=True,
        )
        print(f"--- OTP {otp} sent to {user.email} ---")

        return Response({"detail": "OTP sent to your email for verification."}, status=status.HTTP_201_CREATED)

class VerifyOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        otp = request.data.get('otp')
        try:
            user = User.objects.get(email=email)
            if user.otp == otp and user.otp_expiry > timezone.now():
                user.is_active = True
                user.is_verified = True
                user.otp = None
                user.otp_expiry = None
                user.save()
                return Response({'detail': 'Account verified successfully!'}, status=status.HTTP_200_OK)
            else:
                return Response({'detail': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

class ResendOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        try:
            user = User.objects.get(email=email)
            if user.is_verified:
                return Response({'detail': 'Account is already verified.'}, status=status.HTTP_400_BAD_REQUEST)
            
            otp = str(random.randint(1000, 9999))
            user.otp = otp
            user.otp_expiry = timezone.now() + timedelta(minutes=5)
            user.save()

            send_mail('Your New OTP for Produit Academy', f'Your new OTP is: {otp}', 'from@produit.academy', [user.email], fail_silently=True)
            return Response({'detail': 'A new OTP has been sent to your email.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

class ChangePasswordView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer
    def get_object(self):
        return self.request.user

class PasswordResetRequestOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        email = request.data.get('email')
        try:
            user = User.objects.get(email=email)
            
            # Generate and save a new OTP
            otp = str(random.randint(1000, 9999))
            user.otp = otp
            user.otp_expiry = timezone.now() + timedelta(minutes=5)
            user.save()
            
            # Send the OTP email
            send_mail('Password Reset OTP for Produit Academy', f'Your OTP to reset your password is: {otp}', 'from@produit.academy', [user.email], fail_silently=True)
            print(f"--- Password Reset OTP {otp} sent to {user.email} ---")
            
            return Response({'detail': 'OTP has been sent to your email.'})
        except User.DoesNotExist:
            return Response({'detail': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)

class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        email = request.data.get('email')
        otp = request.data.get('otp')
        password = request.data.get('password')

        try:
            user = User.objects.get(email=email)
            if user.otp == otp and user.otp_expiry > timezone.now():
                user.set_password(password)
                user.otp = None # Clear OTP fields
                user.otp_expiry = None
                user.save()
                return Response({'detail': 'Password has been reset successfully.'})
            else:
                return Response({'detail': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'detail': 'An error occurred.'}, status=status.HTTP_400_BAD_REQUEST)

class StudentDashboardView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer
    def get_object(self):
        return self.request.user

class AdminDashboardView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = CourseRequest.objects.filter(status='Pending')
    serializer_class = CourseRequestSerializer

class StudyMaterialView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudyMaterialSerializer
    def get_queryset(self):
        user = self.request.user
        try:
            course_request = CourseRequest.objects.get(student=user)
            if course_request.status == 'Approved':
                return StudyMaterial.objects.filter(branch=course_request.branch)
            else:
                return StudyMaterial.objects.filter(branch=course_request.branch, is_preview=True)
        except CourseRequest.DoesNotExist:
            return StudyMaterial.objects.none()

class StudyMaterialUploadView(generics.CreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    queryset = StudyMaterial.objects.all()
    serializer_class = StudyMaterialSerializer

class CourseRequestUpdateView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = CourseRequest.objects.all()
    serializer_class = CourseRequestSerializer
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        new_status = request.data.get('status')
        if new_status in ['Approved', 'Rejected']:
            instance.status = new_status
            instance.save()
            return Response(self.get_serializer(instance).data)
        return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

class BranchListView(generics.ListAPIView):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [permissions.AllowAny]

class CourseRequestView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CourseRequestSerializer
    def get_queryset(self):
        return CourseRequest.objects.filter(student=self.request.user)

class StudentListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(role='student', is_active=True)
    serializer_class = UserSerializer

class StudentManageView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer
    def get_object(self):
        return self.request.user

# This is the view for serving the PDF file directly.
# It will be used by the Google Docs viewer when the site is deployed.
class MaterialFileView(generics.GenericAPIView):
    # This is intentionally not authenticated for the Google Viewer to work
    permission_classes = [permissions.AllowAny] 
    queryset = StudyMaterial.objects.all()

    def get(self, request, *args, **kwargs):
        try:
            material = self.get_object()
            file_handle = material.file.open()
            response = FileResponse(file_handle, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{material.file.name}"'
            return response
        except Http404:
            return Response({"detail": "Material not found."}, status=status.HTTP_404_NOT_FOUND)