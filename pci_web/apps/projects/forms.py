from django import forms
from .models import Project, ProjectImage


class ProjectCreateForm(forms.ModelForm):
    name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Project Name",
        required=True,
    )
    lat = forms.CharField(widget=forms.HiddenInput(), required=False)
    lng = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = Project
        fields = ["name", "lat", "lng"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_name(self):
        name = self.cleaned_data["name"]
        if self.user and Project.objects.filter(user=self.user, name=name).exists():
            raise forms.ValidationError("Project name already exists")
        return name




class MultipleFileInput(forms.FileInput):
    allow_multiple_selected = True          # ← THIS LINE FIXES THE ERROR

    def __init__(self, attrs=None):
        super().__init__(attrs)
    
    def value_from_datadict(self, data, files, name):
        return files.getlist(name)


class ImageUploadForm(forms.ModelForm):
    image = forms.FileField(
        widget=MultipleFileInput(
            attrs={
                "class": "custom-file-input",
                "multiple": True,
                "accept": "image/jpeg,image/jpg,image/png",
            }
        ),
    )

    class Meta:                     # ← removed duplicate Meta
        model = ProjectImage
        fields = ["image"]