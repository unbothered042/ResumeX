from django.shortcuts import render

# Create your views here.

from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Analysis
from .serializers import AnalysisSerializer
from .ai_service import analyze_cv, rewrite_cv, generate_cover_letter, generate_cv_pdf, generate_cover_letter_pdf
from django.http import FileResponse


class AnalyzeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        job_description = request.data.get('job_description')
        cv_rewrite_requested = request.data.get('cv_rewrite_requested', 'false').lower() == 'true'
        cover_letter_requested = request.data.get('cover_letter_requested', 'false').lower() == 'true'
        cv_file = request.FILES.get('cv_file')
        cv_text = request.data.get('cv_text')

        if not job_description:
            return Response({'error': 'job_description is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if cv_file:
            filename = (cv_file.name or '').lower()

            if filename.endswith('.pdf'):
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(cv_file)
                    cv_text = ""
                    for page in pdf_reader.pages:
                        cv_text += page.extract_text()
                    if not cv_text.strip():
                        return Response({'error': 'Could not extract text from PDF.'}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response({'error': f'Failed to read PDF: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            elif filename.endswith('.docx'):
                try:
                    import docx
                    document = docx.Document(cv_file)
                    cv_text = "\n".join(p.text for p in document.paragraphs)
                    if not cv_text.strip():
                        return Response({'error': 'Could not extract text from Word document.'}, status=status.HTTP_400_BAD_REQUEST)
                except Exception as e:
                    return Response({'error': f'Failed to read Word document: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

            elif filename.endswith('.doc'):
                return Response(
                    {'error': 'Older .doc files are not supported. Please save your CV as .docx or .pdf and try again.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            else:
                return Response({'error': 'Unsupported file type. Please upload a PDF or Word (.docx) file.'}, status=status.HTTP_400_BAD_REQUEST)

        elif not cv_text:
            return Response({'error': 'Either cv_file (PDF or DOCX) or cv_text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # CV rewrite and cover letter require login
        if cv_rewrite_requested or cover_letter_requested:
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Please create a free account to access CV rewrite and cover letter features.', 'requires_auth': True},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        ai_result = analyze_cv(cv_text, job_description)

        # Only save to database if user is logged in
        if request.user.is_authenticated:
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
                cover_letter_requested=cover_letter_requested,
            )

            if cv_rewrite_requested:
                rewritten = rewrite_cv(cv_text, job_description, ai_result['matched_skills'], ai_result['missing_skills'], ai_result['improvement_tips'])
                analysis.rewritten_cv = rewritten
                analysis.save()

            if cover_letter_requested:
                cover_letter = generate_cover_letter(cv_text, job_description, ai_result['matched_skills'], ai_result['improvement_tips'])
                analysis.cover_letter = cover_letter
                analysis.save()

            serializer = AnalysisSerializer(analysis)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        # Guest user — return analysis without saving
        return Response({
            'id': None,
            'match_score': ai_result['match_score'],
            'matched_skills': ai_result['matched_skills'],
            'missing_skills': ai_result['missing_skills'],
            'improvement_tips': ai_result['improvement_tips'],
            'summary': ai_result['summary'],
            'cv_rewrite_requested': False,
            'rewritten_cv': None,
            'cover_letter_requested': False,
            'cover_letter': None,
            'guest': True,
        }, status=status.HTTP_200_OK)


class AnalysisHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        analyses = Analysis.objects.filter(user=request.user).order_by('-created_at')
        serializer = AnalysisSerializer(analyses, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            serializer = AnalysisSerializer(analysis)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)

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
                return Response({'error': 'No rewritten CV found.'}, status=status.HTTP_404_NOT_FOUND)
            full_name = f"{request.user.first_name} {request.user.last_name}"
            pdf_buffer = generate_cv_pdf(analysis.rewritten_cv, full_name)
            return FileResponse(pdf_buffer, as_attachment=True, filename=f"CVX_{full_name.replace(' ', '_')}.pdf", content_type='application/pdf')
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)


class DownloadCoverLetterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            analysis = Analysis.objects.get(id=id, user=request.user)
            if not analysis.cover_letter:
                return Response({'error': 'No cover letter found.'}, status=status.HTTP_404_NOT_FOUND)
            full_name = f"{request.user.first_name} {request.user.last_name}"
            pdf_buffer = generate_cover_letter_pdf(analysis.cover_letter, full_name)
            return FileResponse(pdf_buffer, as_attachment=True, filename=f"CVX_CoverLetter_{full_name.replace(' ', '_')}.pdf", content_type='application/pdf')
        except Analysis.DoesNotExist:
            return Response({'error': 'Analysis not found.'}, status=status.HTTP_404_NOT_FOUND)