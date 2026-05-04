from django.shortcuts import render

# Create your views here.

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Analysis
from .serializers import AnalysisSerializer
from .ai_service import analyze_cv, rewrite_cv
from django.http import FileResponse
from .ai_service import generate_cv_pdf


class AnalyzeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        job_description = request.data.get('job_description')
        cv_rewrite_requested = request.data.get('cv_rewrite_requested', 'false').lower() == 'true'
        cv_file = request.FILES.get('cv_file')
        cv_text = request.data.get('cv_text')

        if not job_description:
            return Response(
                {'error': 'job_description is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Handle PDF upload
        if cv_file:
            try:
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(cv_file)
                cv_text = ""
                for page in pdf_reader.pages:
                    cv_text += page.extract_text()
                if not cv_text.strip():
                    return Response(
                        {'error': 'Could not extract text from PDF. Please try a different file.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Exception as e:
                return Response(
                    {'error': f'Failed to read PDF: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif not cv_text:
            return Response(
                {'error': 'Either cv_file (PDF) or cv_text is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        ai_result = analyze_cv(cv_text, job_description)

        analysis = Analysis.objects.create(
            user=request.user,
            cv_text=cv_text,
            job_description=job_description,
            match_score=ai_result['match_score'],
            matched_skills=ai_result['matched_skills'],
            missing_skills=ai_result['missing_skills'],
            improvement_tips=ai_result['improvement_tips'],
            summary=ai_result['summary'],
            cv_rewrite_requested=cv_rewrite_requested,
        )

        if cv_rewrite_requested:
            rewritten = rewrite_cv(
                cv_text,
                job_description,
                ai_result['matched_skills'],
                ai_result['missing_skills'],
                ai_result['improvement_tips'],
            )
            analysis.rewritten_cv = rewritten
            analysis.save()

        serializer = AnalysisSerializer(analysis)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses = Analysis.objects.filter(user=request.user).order_by('-created_at')
        serializer = AnalysisSerializer(analyses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            analysis.delete()
            return Response({'message': 'Analysis deleted successfully.'}, status=status.HTTP_200_OK)
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)


class DownloadRewrittenCVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)

            if not analysis.rewritten_cv:
                return Response(
                    {'error': 'No rewritten CV found for this analysis.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            full_name = f"{request.user.first_name} {request.user.last_name}"
            pdf_buffer = generate_cv_pdf(analysis.rewritten_cv, full_name)

            return FileResponse(
                pdf_buffer,
                as_attachment=True,
                filename=f"ResumeX_{full_name.replace(' ', '_')}.pdf",
                content_type='application/pdf'
            )

        except Analysis.DoesNotExist:
            return Response(
                {'error': 'Analysis not found.'},
                status=status.HTTP_404_NOT_FOUND
            )