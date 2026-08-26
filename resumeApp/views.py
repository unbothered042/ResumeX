from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Analysis, LEVEL_CHOICES, GuestUsage
from .serializers import AnalysisSerializer
from .ai_service import analyze_cv, rewrite_cv, generate_cover_letter, generate_cv_pdf, generate_cover_letter_pdf
from accounts.models import LEVEL_MIN_TIER, FREE_ANALYSES_LIMIT
from django.http import FileResponse


def get_client_ip(request):
    """Render sits behind a proxy, so the real client IP is in
    X-Forwarded-For, not REMOTE_ADDR."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AnalyzeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        job_description = request.data.get('job_description')
        cv_rewrite_requested = request.data.get('cv_rewrite_requested', 'false').lower() == 'true'
        cover_letter_requested = request.data.get('cover_letter_requested', 'false').lower() == 'true'
        level = request.data.get('level')
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

        # Credit / free-trial gating for logged-in users. Guests keep the
        # existing free-analysis-only flow (no rewrite/cover letter, ever).
        used_free_trial = False
        if request.user.is_authenticated:
            user = request.user

            if cv_rewrite_requested or cover_letter_requested:
                if not level or level not in dict(LEVEL_CHOICES):
                    return Response(
                        {'error': 'A valid level (entry, mid, senior, executive) is required for CV rewrite or cover letter.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if level not in user.unlocked_levels():
                    return Response(
                        {
                            'error': f'Your current plan does not include the {level} level. Upgrade your plan to unlock it.',
                            'requires_upgrade': True,
                        },
                        status=status.HTTP_403_FORBIDDEN
                    )
                if user.analysis_credits < 1:
                    return Response(
                        {'error': 'You are out of credits. Purchase or top up a plan to continue.', 'requires_purchase': True},
                        status=status.HTTP_402_PAYMENT_REQUIRED
                    )
                user.analysis_credits -= 1
                user.save(update_fields=['analysis_credits'])

            else:
                # Plain analysis only — spend a free trial first, then credits.
                if user.free_analyses_remaining > 0:
                    user.free_analyses_used += 1
                    user.save(update_fields=['free_analyses_used'])
                    used_free_trial = True
                elif user.analysis_credits >= 1:
                    user.analysis_credits -= 1
                    user.save(update_fields=['analysis_credits'])
                else:
                    return Response(
                        {'error': 'Your free analyses are used up. Purchase a plan to continue.', 'requires_purchase': True},
                        status=status.HTTP_402_PAYMENT_REQUIRED
                    )

        else:
            # Guest (unauthenticated) — tracked by IP since there's no account.
            ip = get_client_ip(request)
            guest_usage, _ = GuestUsage.objects.get_or_create(ip_address=ip)
            if guest_usage.analyses_used >= FREE_ANALYSES_LIMIT:
                return Response(
                    {
                        'error': 'You have used your free analyses. Create a free account to continue.',
                        'requires_auth': True,
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )
            guest_usage.analyses_used += 1
            guest_usage.save(update_fields=['analyses_used'])

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
                level=level if (cv_rewrite_requested or cover_letter_requested) else None,
            )

            if cv_rewrite_requested:
                rewritten = rewrite_cv(cv_text, job_description, ai_result['matched_skills'], ai_result['missing_skills'], ai_result['improvement_tips'], level=level)
                analysis.rewritten_cv = rewritten
                analysis.save()

            if cover_letter_requested:
                cover_letter = generate_cover_letter(cv_text, job_description, ai_result['matched_skills'], ai_result['improvement_tips'], level=level)
                analysis.cover_letter = cover_letter
                analysis.save()

            serializer = AnalysisSerializer(analysis)
            response_data = dict(serializer.data)
            response_data['analysis_credits'] = request.user.analysis_credits
            response_data['free_analyses_remaining'] = request.user.free_analyses_remaining
            response_data['used_free_trial'] = used_free_trial
            return Response(response_data, status=status.HTTP_201_CREATED)

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